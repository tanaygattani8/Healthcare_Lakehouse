# Readmission decision gate — dev tier

Window: **30 days** from discharge.

| Measure | Value |
|---|---:|
| Inpatient encounters | 1,292 |
| Excluded — died at index | 24 |
| Excluded — insufficient follow-up | 3 |
| **Index admissions** | **1,265** |
| **Readmissions** | **202** |
| **Base rate** | **15.97%** |

## Verdict

**PROCEED.** The label has enough positive cases and a plausible base rate. Note that it remains synthetic — absolute model performance is meaningless and must be stated as such.

## Definitions

- **Index admission** — `ENCOUNTERCLASS = 'inpatient'`, excluding admissions
  where the patient died on or before discharge, and excluding admissions with
  fewer than 30 days of follow-up before the end of the data.
- **Readmission** — a later inpatient admission for the same patient, strictly
  more than 0 and at most 30 days after the index discharge.
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
