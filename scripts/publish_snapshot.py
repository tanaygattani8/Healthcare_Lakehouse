from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import dbx
from scripts.entities import ENTITIES
from scripts.readmission_model import FEATURES, GRID, POPULATIONS
from scripts.readmission_story import (
    SIGNALS,
    SUPPRESS_BELOW,
    Side,
    complete_suppression,
    hidden_sum,
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
# Phase 6: the model's comparison and drift, from the ml tables the notebooks
# write. The latest drift run only; earlier runs are history for phase 8.
MODEL_RESULTS = "SELECT * FROM {catalog}.ml.model_results"
MANIFEST = ("SELECT current_timestamp() AS captured_at, "
            "to_date(from_utc_timestamp(max(started_at), 'America/Chicago')) AS data_through "
            "FROM {catalog}.silver.encounter")
MODEL_DRIFT = ("SELECT drift_check, period, subject, value, low, high, status "
               "FROM {catalog}.ml.drift_report "
               "WHERE run_at = (SELECT max(run_at) FROM {catalog}.ml.drift_report)")
MODEL_TEXT = {"population", "patients", "scorer", "model_kind", "model_version", "model_verdict",
              "cutoff_verdict"}
# Phase 9: the retraining loop's decisions. ml.retrain_history holds rates and
# verdicts only (D75); the stay count per window is in the hundreds.
RETRAIN_HISTORY = (
    "SELECT as_of, mode, champion_version, check_stays, target, champion_rate, "
    "champion_low, champion_high, triggered, cutoff_rate, cutoff_workload, retrain_rate, "
    "retrain_workload, retrain_ranking, outcome, new_version, shifted_features "
    "FROM {catalog}.ml.retrain_history ORDER BY written_at")
RETRAIN_TEXT = {"mode", "champion_version", "cutoff_workload", "retrain_workload",
                "retrain_ranking", "outcome", "new_version", "shifted_features", "triggered"}
# The five commonest admit reasons (Task 2 Step 5), pasted, so the guard
# stays a fixed list. A new name stops the publish until it is checked.
ADMIT_REASONS = {
    "Dependent drug abuse (disorder)",
    "Sterilization requested (situation)",
    "History of coronary artery bypass grafting (situation)",
    "Appendicitis (disorder)",
    "Sleep disorder (disorder)",
}
# Phase 8's dashboard (D74), default view: every filter "All". Its own SQL, so
# the app shows what the dashboard shows and shown() runs in one place.
BOARD = Path(__file__).resolve().parents[1] / "dashboards" / "operations.lvdash.json"
OPS_DATASETS = ("kpi_visits", "kpi_stays", "kpi_readmission", "visits_trend",
                "stays_trend", "by_payer", "by_hospital")
OPS_WINDOW = ("SELECT window_start, last_month, prior_start, prior_end "
              "FROM {catalog}.metrics.kpi_window")
# Synthea's hospitals and insurers are real names. Synthetic costs beside them
# would read as claims about them, so only government programmes keep a name.
PROGRAMMES = {"Medicare": "Medicare", "Medicaid": "Medicaid", "Dual Eligible": "Dual Eligible",
              "NO_INSURANCE": "No insurance"}
VISIT_TYPES = {"ambulatory", "emergency", "inpatient", "other", "outpatient", "urgentcare",
               "wellness"}
ALLOWED_TEXT = {
    "payer": set(PROGRAMMES.values()) | {f"Commercial payer {i}" for i in range(1, 51)},
    "hospital": {f"Hospital {chr(c)}" for c in range(ord("A"), ord("Z") + 1)},
    "visit_type": VISIT_TYPES,
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
    "population": set(POPULATIONS),
    "patients": {"all", "new", "returning"},
    "scorer": {"base_rate", "rule", "model"},
    "model_kind": set(GRID),
    "model_verdict": {"beats", "no better", "too few to judge"},
    "cutoff_verdict": {"beats", "no better", "too few to judge"},
    "drift_check": {"feature", "score", "flag_rate", "readmission_rate"},
    "period": {"training", "2020-2026"} | {str(year) for year in range(2020, 2027)},
    "subject": set(FEATURES) | set(POPULATIONS),
    "status": {"stable", "watch", "shifted", "reference"},
    "mode": {"replay", "live"},
    "outcome": {"no trigger", "none passed", "new cutoff", "retrain"},
    "cutoff_workload": {"pass", "fail"},
    "retrain_workload": {"pass", "fail"},
    "retrain_ranking": {"not worse", "clearly worse", "not judged"},
    # Registry versions: digits only, so nothing else can ride in this column.
    "champion_version": {str(v) for v in range(1, 100)},
    "new_version": {str(v) for v in range(1, 100)},
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
    1-10, a signal with exactly one hidden level, or hidden levels that hold
    1-10 stays or readmissions between them (D79)."""
    shown = levels[~levels["suppressed"]]
    for column in ("index_stays", "readmitted", "rest_stays", "rest_readmitted"):
        if shown[column].between(1, SUPPRESS_BELOW - 1).any():
            raise SystemExit(f"refusing to publish: a shown {column} is 1-10")
    hidden = levels.groupby("signal")["suppressed"].sum()
    if (hidden == 1).any():
        raise SystemExit("refusing to publish: a signal has exactly one hidden level")
    for signal, rows in levels.groupby("signal"):
        left = hidden_sum(rows.to_dict("records"))
        if left and (0 < left.stays < SUPPRESS_BELOW
                     or 0 < left.readmitted < SUPPRESS_BELOW):
            raise SystemExit(f"refusing to publish: the hidden levels of {signal} "
                             "hold 1-10 between them")


def _numbers(df: pd.DataFrame, text: set[str]) -> pd.DataFrame:
    # The SQL connector returns NULL as None, which makes a number column
    # object-typed, and check_only_categories would read it as text.
    numeric = [c for c in df.columns if c not in text]
    return df.astype(dict.fromkeys(numeric, float))


def publish_model_results(results: pd.DataFrame) -> pd.DataFrame:
    """Hide a recall built on 1-10 readmissions caught or missed (D66), then
    drop every count, so no count reaches the parquet (decision P-d)."""
    results = _numbers(results, MODEL_TEXT)
    small = (results["caught"].between(1, SUPPRESS_BELOW - 1)
             | results["missed"].between(1, SUPPRESS_BELOW - 1))
    # The rule is 0/1, so its average precision (c^2/(R*F) + (R-c)/N) and its
    # Brier score are functions of the counts: hidden with its recall (D72).
    # The model's are ranking and calibration scores, and stay.
    rule_small = small & (results["scorer"] == "rule")
    results = results.assign(recall=results["recall"].mask(small),
                             avg_precision=results["avg_precision"].mask(rule_small),
                             brier=results["brier"].mask(rule_small))
    # A new/returning breakdown publishes its verdict only: its base-rate
    # precision is readmitted / stays, and some breakdowns hold 1-10 (D72).
    numbers = [c for c in results.columns if c not in MODEL_TEXT]
    results.loc[results["patients"] != "all", numbers] = np.nan
    # Rounded, so no published rate can be turned back into exact counts.
    return (results.round(4)
                   .drop(columns=["readmitted", "caught", "missed", "k", "model_version"]))


def publish_drift(drift: pd.DataFrame) -> pd.DataFrame:
    # Three decimals: an exact training rate (k / n), with the published
    # totals, would give the 1-10 gap readmissions back by subtraction (D72).
    # The training readmission rate is left out entirely: with the published
    # totals it narrows the gap's 1-10 readmissions to a handful (D72). The
    # 2020-2026 row's status still says whether training's rate fits.
    drift = drift[~((drift["drift_check"] == "readmission_rate")
                    & (drift["period"] == "training"))].reset_index(drop=True)
    return _numbers(drift, {"drift_check", "period", "subject", "status"}).round(3)


def publish_retrain_history(history: pd.DataFrame) -> pd.DataFrame:
    """The retraining loop's rows (D75), refused if anything in them is not a
    rate, a known label or a feature name, or if a count could be 1-10."""
    history = _numbers(history.assign(as_of=pd.to_datetime(history["as_of"]),
                                      triggered=history["triggered"].astype(bool)),
                       RETRAIN_TEXT | {"as_of"})
    shifted = {name for cell in history["shifted_features"].dropna()
               for name in cell.split(",") if name}
    if shifted - set(FEATURES):
        raise SystemExit("refusing to publish: shifted_features holds a name that is not a feature")
    # The window size, and the flagged stays a rate implies, must not be 1-10.
    flagged = (history["champion_rate"] * history["check_stays"]).round()
    for counts in (history["check_stays"], flagged):
        if counts.between(1, SUPPRESS_BELOW - 1).any():
            raise SystemExit("refusing to publish: a retraining window implies a 1-10 count")
    check_only_categories(history.drop(columns=["shifted_features", "triggered"]))
    return history


def ops_queries(catalog: str) -> dict[str, tuple[str, dict]]:
    """Each dataset's SQL from the exported dashboard, with its filters at "All"."""
    board = json.loads(BOARD.read_text(encoding="utf-8"))
    return {ds["name"]: ("".join(ds["queryLines"]).replace("healthcare_dev.", f"{catalog}."),
                         {p["keyword"]: "All" for p in ds.get("parameters", [])})
            for ds in board["datasets"] if ds["name"] in OPS_DATASETS}


def _ops_frame(df: pd.DataFrame, text: set[str] = frozenset(),
               dates: tuple[str, ...] = ()) -> pd.DataFrame:
    df = _numbers(df, set(text) | set(dates))
    return df.assign(**{c: pd.to_datetime(df[c]) for c in dates})


def publish_ops(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """The dashboard's default view with made-up hospital and insurer names,
    refused if a count is 1-10 or subtraction against a tile gives one back."""
    kpi = pd.concat([raw[n] for n in ("kpi_visits", "kpi_stays", "kpi_readmission",
                                      "kpi_window")], axis=1)
    # With no filter, share of network is always 100 and every network gap 0.
    kpi = _ops_frame(kpi.drop(columns=[c for c in kpi if "network" in c]),
                     dates=("window_start", "last_month", "prior_start", "prior_end"))
    visits = _ops_frame(raw["visits_trend"], {"visit_type"}, ("visit_month",))
    stays = _ops_frame(raw["stays_trend"], dates=("admit_quarter",))
    payers = _ops_frame(raw["by_payer"], {"payer"})
    commercial = payers.loc[~payers["payer"].isin(PROGRAMMES), "payer"]
    labels = {name: f"Commercial payer {i}" for i, name in enumerate(commercial, 1)}
    payers["payer"] = payers["payer"].map({**PROGRAMMES, **labels})
    hospitals = _ops_frame(raw["by_hospital"], {"hospital"})
    if len(hospitals) > 26:
        raise SystemExit("refusing to publish: more hospitals than letters")
    hospitals["hospital"] = [f"Hospital {chr(ord('A') + i)}" for i in range(len(hospitals))]

    if visits["visits"].isna().any() or stays["stays"].isna().any():
        raise SystemExit("refusing to publish: a hidden trend cell, which the tiles give back")
    small = range(1, SUPPRESS_BELOW)
    for frame, column in ((visits, "visits"), (stays, "stays"), (payers, "stays"),
                          (hospitals, "stays")):
        if frame[column].between(1, SUPPRESS_BELOW - 1).any():
            raise SystemExit(f"refusing to publish: a shown {column} is 1-10")
    total = kpi["stays"].iloc[0]
    if payers["stays"].isna().sum() == 1 or total - payers["stays"].sum() in small:
        raise SystemExit("refusing to publish: the stays tile gives back a hidden payer")
    if total - hospitals["stays"].sum() in small:
        raise SystemExit("refusing to publish: the hospitals left out hold 1-10 stays")
    out = {"ops_kpi": kpi, "ops_visits": visits, "ops_stays": stays, "ops_payers": payers,
           "ops_hospitals": hospitals}
    for frame in out.values():
        check_only_categories(frame)
    return out


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
        # Decided on the real counts (D66), but not published for a hidden
        # level: with the hidden sum, "separates" can pin which side of the
        # rule a hidden level falls on (D81). The verdict below counts it.
        levels["separates"] = levels["separates"].astype("boolean").mask(levels["suppressed"])
        frames["story_levels"] = levels
        frames["story_verdict"] = pd.DataFrame({"decision": [verdict(short)],
                                                "shortlisted": [len(short)]})
        for name in ("story_totals", "story_levels", "story_verdict"):
            check_only_categories(frames[name])
        for name, query, publish in (("model_results", MODEL_RESULTS, publish_model_results),
                                     ("model_drift", MODEL_DRIFT, publish_drift)):
            cur.execute(query.format(catalog=catalog))
            frames[name] = publish(pd.DataFrame(cur.fetchall(),
                                                columns=[d[0] for d in cur.description]))
            check_only_categories(frames[name])
        cur.execute(RETRAIN_HISTORY.format(catalog=catalog))
        frames["retrain_history"] = publish_retrain_history(
            pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description]))
        raw = {}
        for name, (query, params) in [*ops_queries(catalog).items(),
                                      ("kpi_window", (OPS_WINDOW.format(catalog=catalog), {}))]:
            cur.execute(query, params)
            raw[name] = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        frames.update(publish_ops(raw))
        # When this ran, and the last day the data covers, so a page can say
        # how old it is (D81). Two dates, no numbers.
        cur.execute(MANIFEST.format(catalog=catalog))
        manifest = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        frames["manifest"] = manifest.apply(pd.to_datetime)
    return frames


# Every number column of every published file, and what it is (D81). A count
# of people, stays, visits or readmissions must be 0 or 11+; every other role
# says why its column is not one. A column with no role refuses the publish:
# the per-frame guards above check what each frame was known to hold, and
# this is what stops a new column, or a new frame, slipping past them.
COUNT = "count"
ROLES: dict[str, dict[str, str]] = {
    # rows per table; hospitals, providers and payers count businesses (BUSINESS)
    "bronze_counts": {"rows": COUNT},
    # The size of each k-anonymity group, and how many people sit in groups of
    # that size, for a copy never released. A size names no one (D81).
    "deid_kanon": {"groups": "class size", "people": "class size"},
    # name, date and other spans found in 25 test patients' notes: text, not people
    "deid_scores": {"real_items": "text spans", "guesses": "text spans", "precision": "rate",
                    "recall": "rate", "covered_recall": "rate", "exact_recall": "rate"},
    # questions per verdict, out of 20 synthetic questions
    "eval_scores": {"run_no": "label", "tier": "label", "answers": "questions"},
    "gold_care_gap": {"measure_year": "label", "in_denominator": COUNT, "excl_age": COUNT,
                      "excl_died": COUNT, "excl_hospice": COUNT, "eligible": COUNT,
                      "met": COUNT, "gaps": COUNT},
    "model_drift": {"value": "rate", "low": "rate", "high": "rate"},
    "model_results": {c: "rate" for c in ("recall", "avg_precision", "brier", "cv_avg_precision",
                                          "diff_low", "diff_mid", "diff_high",
                                          "cut_low", "cut_mid", "cut_high")},
    "ops_hospitals": {"stays": COUNT, "avg_length_of_stay_days": "average",
                      "length_of_stay_vs_network_days": "average", "cost_per_stay": "money",
                      "cost_vs_network_pct": "rate"},
    "ops_kpi": {"visits": COUNT, "visits_prior": COUNT, "visits_change_pct": "rate",
                "stays": COUNT, "stays_prior": COUNT, "stays_change_pct": "rate",
                "avg_length_of_stay_days": "average",
                "avg_length_of_stay_days_prior": "average",
                "length_of_stay_change_days": "average", "cost_per_stay": "money",
                "cost_per_stay_prior": "money", "cost_change_pct": "rate",
                "readmission_rate_pct_2020_2026": "rate",
                "readmission_rate_pct_2010_2019": "rate"},
    "ops_payers": {"stays": COUNT, "avg_length_of_stay_days": "average",
                   "cost_per_stay": "money"},
    "ops_stays": {"stays": COUNT, "avg_length_of_stay_days": "average",
                  "cost_per_stay": "money"},
    "ops_visits": {"visits": COUNT},
    "retrain_history": {"check_stays": COUNT, "target": "rate", "champion_rate": "rate",
                        "champion_low": "rate", "champion_high": "rate",
                        "cutoff_rate": "rate", "retrain_rate": "rate"},
    "story_levels": {"chapter": "label", "index_stays": COUNT, "readmitted": COUNT,
                     "rest_stays": COUNT, "rest_readmitted": COUNT,
                     **{c: "rate" for c in ("rate", "low", "high",
                                            "rest_rate", "rest_low", "rest_high")}},
    "story_totals": {**{c: COUNT for c in ("stays", "encounters_merged", "excl_died",
                                           "excl_short_followup", "excl_hospice",
                                           "excl_cancer_treatment", "index_stays",
                                           "readmitted", "patients", "readmitted_patients")},
                     "index_stay_cost": "money", "return_stay_cost": "money"},
    # how many signals made the shortlist: signals, not people
    "story_verdict": {"shortlisted": "signals"},
}
BUSINESS = {"organizations", "providers", "payers"}


def check_roles(frames: dict[str, pd.DataFrame]) -> None:
    """Stop before writing anything if a number column has no declared role,
    or a count of people, stays or visits is 1-10 (D66, D81)."""
    for name, df in frames.items():
        for column in df.select_dtypes(include="number").columns:
            role = ROLES.get(name, {}).get(column)
            if role is None:
                raise SystemExit(f"refusing to publish: {name}.{column} has no declared role")
            values = df[column]
            if name == "bronze_counts":
                values = values[~df["entity"].isin(BUSINESS)]
            if role == COUNT and values.between(1, SUPPRESS_BELOW - 1).any():
                raise SystemExit(f"refusing to publish: {name}.{column} holds a count of 1-10")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="healthcare_dev")
    parser.add_argument("--out", type=Path, default=Path("snapshots/bronze_counts.parquet"))
    args = parser.parse_args()

    # Aggregates only. Quarantined rows are patient-shaped records; the public
    # page gets counts, never a sample.
    frames = {args.out.stem: fetch_counts(args.catalog, ENTITIES),
              **fetch_aggregates(args.catalog)}
    check_roles(frames)   # every frame, before any file is written
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        path = args.out.parent / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        print(frame.to_string(index=False))
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
