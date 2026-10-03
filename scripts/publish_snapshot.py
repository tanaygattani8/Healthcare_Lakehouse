from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from scripts import dbx
from scripts.entities import ENTITIES
from scripts.readmission_story import (
    SIGNALS,
    SUPPRESS_BELOW,
    Side,
    complete_suppression,
    level_row,
    shortlist,
    verdict,
)
from scripts.text_to_sql_score import VERDICTS

# Silver tables and the ops.quarantine_* table each one feeds. Kept here rather
# than derived from ENTITIES because silver names are singular and do not map
# one-to-one onto the bronze entity list.
SILVER_TABLES = [
    "patient", "encounter", "condition", "observation", "medication",
    "procedure", "immunization", "allergy", "careplan",
]


def build_count_query(catalog: str, entities: list[str]) -> str:
    parts = [
        f"SELECT 'bronze' AS layer, '{e}' AS entity, count(*) AS rows "
        f"FROM {catalog}.bronze.br_{e}"
        for e in entities
    ]
    parts += [
        f"SELECT 'silver', '{t}', count(*) FROM {catalog}.silver.{t}"
        for t in SILVER_TABLES
    ]
    parts += [
        f"SELECT 'quarantine', '{t}', count(*) FROM {catalog}.ops.quarantine_{t}"
        for t in SILVER_TABLES
    ]
    return "\nUNION ALL\n".join(parts) + "\nORDER BY layer, rows DESC"


def fetch_counts(catalog: str, entities: list[str]) -> pd.DataFrame:
    with dbx.connect() as conn, conn.cursor() as cur:
        cur.execute(build_count_query(catalog, entities))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["layer", "entity", "rows"])
    df["captured_at"] = dt.datetime.now(dt.UTC)
    return df


# Phase 3b: how well patient details were hidden. Both tables hold counts and
# category labels only, and check_only_categories() refuses anything else — a
# de-identification page that leaked a name would be the worst possible bug.
DEID_SNAPSHOTS = {
    "deid_scores": "SELECT stage, phi_category, real_items, guesses, precision, "
                   "recall, covered_recall, exact_recall FROM {catalog}.ops.detection_score",
    "deid_kanon": "SELECT version, k, groups, people FROM {catalog}.ops.kanon_spread",
}
# Phase 4: gold, which is as private as silver (exact visit dates), so counts
# per measure only, never a row per patient or per stay.
GOLD_SNAPSHOTS = {
    "gold_care_gap": (
        "SELECT measure, measure_year, count(*) AS in_denominator, "
        "count_if(excl_age) AS excl_age, count_if(excl_died) AS excl_died, "
        "count_if(excl_hospice) AS excl_hospice, "
        "count_if(NOT (excl_age OR excl_died OR excl_hospice)) AS eligible, "
        "count_if(numerator_met AND NOT (excl_age OR excl_died OR excl_hospice)) AS met, "
        "count_if(gap) AS gaps "
        "FROM {catalog}.gold.care_gap GROUP BY measure, measure_year"),
}
# Phase 5: the readmission story, read from the metric views so the page
# shows the numbers defined there. Counts per signal level only; a level
# with 1-10 stays or readmissions is hidden, with a complement (D66).
STORY_TOTALS = """
SELECT s.*, r.* FROM
  (SELECT MEASURE(stays) AS stays, MEASURE(encounters_merged) AS encounters_merged,
          MEASURE(excluded_died) AS excl_died,
          MEASURE(excluded_short_followup) AS excl_short_followup,
          MEASURE(excluded_hospice) AS excl_hospice,
          MEASURE(excluded_cancer_treatment) AS excl_cancer_treatment
   FROM {catalog}.metrics.stays) s
CROSS JOIN
  (SELECT MEASURE(index_stays) AS index_stays, MEASURE(readmitted) AS readmitted,
          MEASURE(patients) AS patients, MEASURE(readmitted_patients) AS readmitted_patients,
          CAST(MEASURE(index_stay_cost) AS DOUBLE) AS index_stay_cost,
          CAST(MEASURE(return_stay_cost) AS DOUBLE) AS return_stay_cost
   FROM {catalog}.metrics.readmission) r"""
STORY_MEASURES = "MEASURE(index_stays), MEASURE(readmitted), MEASURE(readmitted_patients)"

# Phase 5: verdict counts only. The run number is published, not the run id
# text; the harness forces run ids to dev-N / test-N.
EVAL_SNAPSHOTS = {
    "eval_scores": (
        "SELECT set_name, CAST(split(run_id, '-')[1] AS INT) AS run_no, "
        "contestant, tier, verdict, count(*) AS answers "
        "FROM {catalog}.ops.eval_run GROUP BY ALL"),
}
# The five commonest admit reasons (Task 2 Step 5), pasted, so the guard
# stays a fixed list. A new name stops the publish until it is checked.
ADMIT_REASONS = {
    "Dependent drug abuse (disorder)",
    "Sterilization requested (situation)",
    "History of coronary artery bypass grafting (situation)",
    "Appendicitis (disorder)",
    "Sleep disorder (disorder)",
}
ALLOWED_TEXT = {
    "measure": {"diabetes_hba1c", "bp_control", "statin_therapy"},
    "stage": {"roster", "regex", "ner", "llm"},
    "phi_category": {"name", "date", "age", "geography", "other_id", "zip"},
    "version": {"plan", "safe", "released"},
    "k": {"1", "2", "3", "4", "5-10", "11+"},
    "signal": set(SIGNALS),
    "level": {"0-17", "18-44", "45-64", "65-79", "80+", "M", "F", "true", "false",
              "0", "1", "2+", "1+", "other"} | ADMIT_REASONS
             | {"1915-1989", "1990-1999", "2000-2009", "2010-2019", "2020-2026"},
    "decision": {"GO", "NO-GO"},
    "set_name": {"dev", "test"},
    "contestant": {"answer_key", "raw", "metrics", "genie"},
    "verdict": set(VERDICTS),
}


def check_only_categories(df: pd.DataFrame) -> None:
    """Stop before writing if any text column holds a value we did not expect."""
    for column in df.select_dtypes(include="object").columns:
        unexpected = set(df[column].dropna()) - ALLOWED_TEXT.get(column, set())
        if unexpected:
            raise SystemExit(f"refusing to publish: column {column!r} has "
                             f"{len(unexpected)} value(s) that are not known categories")


def fetch_story_levels(cur, catalog: str) -> pd.DataFrame:
    """Every signal level against the rest of the index stays. Signal names
    come from the fixed SIGNALS dict, never from input; the level is a bound
    parameter."""
    view = f"{catalog}.metrics.readmission"
    rows = []
    for signal in SIGNALS:
        cur.execute(f"SELECT cast({signal} AS STRING) AS level, {STORY_MEASURES} "
                    f"FROM {view} GROUP BY ALL")
        for level, stays, readmitted, patients in cur.fetchall():
            # A NULL level would make "<> :level" match nothing.
            assert level is not None, f"{signal} has a NULL level"
            cur.execute(f"SELECT {STORY_MEASURES} FROM {view} "
                        f"WHERE cast({signal} AS STRING) <> :level", {"level": level})
            rest = Side(*cur.fetchone())
            rows.append(level_row(signal, level, Side(stays, readmitted, patients), rest))
    levels = pd.DataFrame(complete_suppression(rows))
    check_small_cells(levels)
    return levels


def check_small_cells(levels: pd.DataFrame) -> None:
    """Stop before writing if a published level breaks D66: a shown count of
    1-10, or a signal with exactly one hidden level."""
    shown = levels[~levels["suppressed"]]
    for column in ("index_stays", "readmitted", "rest_stays", "rest_readmitted"):
        if shown[column].between(1, SUPPRESS_BELOW - 1).any():
            raise SystemExit(f"refusing to publish: a shown {column} is 1-10")
    hidden = levels.groupby("signal")["suppressed"].sum()
    if (hidden == 1).any():
        raise SystemExit("refusing to publish: a signal has exactly one hidden level")


def fetch_aggregates(catalog: str) -> dict[str, pd.DataFrame]:
    frames = {}
    with dbx.connect() as conn, conn.cursor() as cur:
        for name, query in {**DEID_SNAPSHOTS, **GOLD_SNAPSHOTS, **EVAL_SNAPSHOTS}.items():
            cur.execute(query.format(catalog=catalog))
            df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
            check_only_categories(df)
            frames[name] = df
        cur.execute(STORY_TOTALS.format(catalog=catalog))
        frames["story_totals"] = pd.DataFrame(cur.fetchall(),
                                              columns=[d[0] for d in cur.description])
        levels = fetch_story_levels(cur, catalog)
        short = shortlist(zip(levels["signal"], levels["separates"], strict=True))
        frames["story_levels"] = levels
        frames["story_verdict"] = pd.DataFrame({"decision": [verdict(short)],
                                                "shortlisted": [len(short)]})
        for name in ("story_totals", "story_levels", "story_verdict"):
            check_only_categories(frames[name])
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="healthcare_dev")
    parser.add_argument("--out", type=Path, default=Path("snapshots/bronze_counts.parquet"))
    args = parser.parse_args()

    df = fetch_counts(args.catalog, ENTITIES)
    # Aggregates only. Quarantined rows are patient-shaped records; the public
    # page gets counts, never a sample.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(df.to_string(index=False))
    print(f"Wrote {args.out}")

    for name, frame in fetch_aggregates(args.catalog).items():
        path = args.out.parent / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        print(frame.to_string(index=False))
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
