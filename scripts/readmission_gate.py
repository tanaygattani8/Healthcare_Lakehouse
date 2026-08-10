"""Phase 1 decision gate: is 30-day readmission a viable ML target on this data?

Runs locally in DuckDB rather than on Databricks. The gate must be cheap and
must not consume Free Edition quota, and it has to answer before anything is
built on top of the label.

Synthea generates patients from explicit rule-based disease modules, so a
supervised model trained on it learns the generator's rules rather than
clinical reality. If the base rate here is degenerate, the eventual ML target
pivots to cost/utilization or care-gap prediction. Finding that out now is the
entire point of this script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

# ponytail: LEAD orders by admission, so when two inpatient stays overlap the
# lookahead can land on a stay that began before this one discharged, and the
# genuine next admission is never seen. 122 of 1,292 dev-tier inpatient
# encounters overlap this way. The correct fix is merging overlapping stays and
# transfers into a single index admission (CMS methodology) — that belongs in
# phase 4's gold layer, not in a gate that only has to answer "plausible?".
# Measured cost of the shortcut on the dev tier: base rate 15.97% here vs
# 19.37% for a min-after-discharge lookahead, which over-counts in the mirror
# image by attributing one readmission to two index stays. Both sit inside the
# real-world 15-20% band and both return the same verdict.
GATE_SQL = """
WITH inp AS (
    SELECT
        "Id"      AS encounter_id,
        "PATIENT" AS patient_id,
        CAST("START" AS TIMESTAMP) AS admitted,
        CAST("STOP"  AS TIMESTAMP) AS discharged
    FROM read_csv_auto($enc, header=true)
    WHERE lower("ENCOUNTERCLASS") = 'inpatient'
),
bounds AS (
    SELECT max(discharged) AS data_end FROM inp
),
sequenced AS (
    SELECT
        inp.*,
        LEAD(admitted) OVER (PARTITION BY patient_id ORDER BY admitted) AS next_admitted
    FROM inp
),
deaths AS (
    SELECT "Id" AS patient_id, TRY_CAST("DEATHDATE" AS DATE) AS death_date
    FROM read_csv_auto($pat, header=true)
),
flagged AS (
    SELECT
        s.*,
        (d.death_date IS NOT NULL AND d.death_date <= CAST(s.discharged AS DATE))
            AS died_at_index,
        (date_diff('day', s.discharged, b.data_end) < $window)
            AS short_followup,
        -- date_diff counts calendar-day boundaries crossed, not elapsed 24h
        -- periods. That is deliberate and matches CMS: a Tuesday 23:00
        -- discharge followed by a Wednesday 02:00 admission is 1 day, not 0.
        -- The > 0 test is what makes same-day re-entry a transfer.
        (s.next_admitted IS NOT NULL
         AND date_diff('day', s.discharged, s.next_admitted) > 0
         AND date_diff('day', s.discharged, s.next_admitted) <= $window)
            AS readmitted
    FROM sequenced s
    CROSS JOIN bounds b
    LEFT JOIN deaths d ON d.patient_id = s.patient_id
)
SELECT
    count(*)                                              AS inpatient_encounters,
    count(*) FILTER (WHERE died_at_index)                 AS excluded_death,
    count(*) FILTER (WHERE short_followup
                     AND NOT died_at_index)               AS excluded_short_followup,
    count(*) FILTER (WHERE NOT died_at_index
                     AND NOT short_followup)              AS index_admissions,
    count(*) FILTER (WHERE NOT died_at_index
                     AND NOT short_followup
                     AND readmitted)                      AS readmissions
FROM flagged
"""


def compute_gate(
    con: duckdb.DuckDBPyConnection,
    encounters_csv: Path,
    patients_csv: Path,
    window_days: int = 30,
) -> dict:
    row = con.execute(
        GATE_SQL,
        {"enc": str(encounters_csv), "pat": str(patients_csv), "window": window_days},
    ).fetchone()

    (
        inpatient_encounters,
        excluded_death,
        excluded_short_followup,
        index_admissions,
        readmissions,
    ) = row

    return {
        "inpatient_encounters": inpatient_encounters,
        "excluded_death": excluded_death,
        "excluded_short_followup": excluded_short_followup,
        "index_admissions": index_admissions,
        "readmissions": readmissions,
        "base_rate": (readmissions / index_admissions) if index_admissions else 0.0,
    }


def verdict(result: dict) -> str:
    """Judgement on whether the label is worth modelling."""
    if result["index_admissions"] < 500:
        return (
            "**PIVOT.** Fewer than 500 index admissions is too few to train and "
            "evaluate on. Either scale the population up or change the target."
        )
    if result["base_rate"] < 0.01:
        return (
            "**PIVOT.** A base rate under 1% means almost no positive cases. "
            "Pivot the target to cost/utilization or care-gap prediction."
        )
    if result["base_rate"] > 0.60:
        return (
            "**PIVOT.** A base rate above 60% suggests the label is close to "
            "deterministic in Synthea's generation rules, not a real signal."
        )
    return (
        "**PROCEED.** The label has enough positive cases and a plausible base "
        "rate. Note that it remains synthetic — absolute model performance is "
        "meaningless and must be stated as such."
    )


def render_markdown(result: dict, window_days: int) -> str:
    return f"""# Readmission decision gate — dev tier

Window: **{window_days} days** from discharge.

| Measure | Value |
|---|---:|
| Inpatient encounters | {result['inpatient_encounters']:,} |
| Excluded — died at index | {result['excluded_death']:,} |
| Excluded — insufficient follow-up | {result['excluded_short_followup']:,} |
| **Index admissions** | **{result['index_admissions']:,}** |
| **Readmissions** | **{result['readmissions']:,}** |
| **Base rate** | **{result['base_rate']:.2%}** |

## Verdict

{verdict(result)}

## Definitions

- **Index admission** — `ENCOUNTERCLASS = 'inpatient'`, excluding admissions
  where the patient died on or before discharge, and excluding admissions with
  fewer than {window_days} days of follow-up before the end of the data.
- **Readmission** — a later inpatient admission for the same patient, strictly
  more than 0 and at most {window_days} days after the index discharge.
- **Same-day re-entry is treated as a transfer**, not a readmission.
- The insufficient-follow-up exclusion is the one commonly forgotten. Without
  it, admissions near the end of the data can never be flagged as readmitted,
  silently depressing the base rate.

## Known limitation

Overlapping inpatient stays are counted as separate index admissions rather
than merged into one. The readmission lookahead orders by admission date, so an
overlapping stay can mask a genuine readmission of the stay it overlaps. This
understates the base rate by roughly 3 points at the dev tier. Merging
overlapping stays and transfers into a single index admission is CMS
methodology and is phase 4's job — this gate only has to answer whether the
label is worth building, and that answer is unchanged either way.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("synthea/output"))
    parser.add_argument("--report", type=Path, default=Path("docs/readmission-gate.md"))
    parser.add_argument("--window-days", type=int, default=30)
    args = parser.parse_args()

    con = duckdb.connect()
    csv_dir = args.output_dir / "csv"
    result = compute_gate(
        con, csv_dir / "encounters.csv", csv_dir / "patients.csv", args.window_days
    )

    # Same guard as calibrate.py: a wrong --output-dir must not write a
    # plausible-looking zeroed report over the committed one and exit 0. This
    # report records a go/no-go decision, so a silent zero is worse than a crash.
    if result["inpatient_encounters"] == 0:
        raise SystemExit(f"no inpatient encounters found under {csv_dir}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_markdown(result, args.window_days), encoding="utf-8")

    print(f"index admissions: {result['index_admissions']:,}")
    print(f"readmissions:     {result['readmissions']:,}")
    print(f"base rate:        {result['base_rate']:.2%}")
    print(f"wrote {args.report}")


if __name__ == "__main__":
    main()
