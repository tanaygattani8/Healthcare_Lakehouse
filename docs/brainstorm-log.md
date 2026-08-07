# Healthcare Lakehouse — Brainstorm Log

**Date:** 2026-08-07
**Status:** Design agreed through architecture + phasing. Spec for phases 1–4 not yet written.

---

## 1. What this project is

A healthcare data engineering + AI project built on Databricks Free Edition:
synthetic EHR data → medallion lakehouse → governed PHI layer → analytics → ML,
orchestrated by Airflow, with a publicly deployed front end.

**Chosen concept:** Readmission Risk + Care Gap Engine, with a PHI
de-identification AI centerpiece.

Two alternatives considered and rejected:

- *Clinical Document Intelligence* — strongest AI story, weakest data
  engineering story, and the good version is gated behind PhysioNet
  credentialing.
- *Payer-Provider Claims Integrity* — teaches revenue-cycle vocabulary instead
  of clinical/EHR vocabulary. Better fit for payer-side roles.

## 2. Goals and constraints (from the user)

| Dimension | Answer |
|---|---|
| Purpose | Both portfolio-shaped and deep. Deployable throughout. |
| Budget | $0. Databricks Free Edition only. |
| Timeline | No fixed deadline, depth first. |
| Strong in | Python, SQL |
| New to | Databricks, Airflow, Spark/PySpark, ML modeling |
| Explicit wants | EHR + PII + healthcare terminology, Databricks, Airflow, medallion, ML, analytics + dashboards, hands-on Spark/PySpark |

## 3. Databricks Free Edition — verified constraints

Source: <https://docs.databricks.com/aws/en/getting-started/free-edition-limitations>

- Serverless only. One SQL warehouse, 2X-Small.
- **One active Lakeflow pipeline per pipeline type** → the whole medallion is a
  single declarative pipeline, not three.
- Max 5 concurrent job tasks per account.
- **Exceeding quota shuts down workspace compute for the rest of the day** (in
  extreme cases, the month). This is the binding constraint on data volume.
- Python and SQL only. No Scala, no R.
- Model serving: no GPU, no provisioned throughput, limited endpoints.
- Vector Search: one endpoint, one search unit. No Direct Vector Access.
- Databricks Apps: up to 3, **auto-stop 24h after start/update/redeploy**, and
  sit behind workspace auth so they cannot be shared publicly.
- One workspace, one metastore. No custom storage locations.
- Restricted outbound internet → prefer Databricks Foundation Model APIs over
  external LLM providers.
- Commercial use prohibited (irrelevant for a portfolio project).

**Verified separately:** Personal Access Tokens *are* available on Free Edition
(Settings → Developer → Access Tokens). This is what unblocks Airflow, dbt, and
Streamlit — all three authenticate the same way. Had this been closed, the
entire external-orchestration design would have collapsed.

## 4. Data sources

**Primary: Synthea** (MITRE, open source). Synthetic patients with full
birth-to-death records. Exports FHIR R4, CSV, C-CDA, and free-text clinical
notes via `ClinicalNoteExporter` into a `notes/` directory.

Two shortcuts worth using:

- MITRE publishes pre-generated datasets.
- A [30,000-patient set exists on Harvard Dataverse](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/BWDKXS).

Generate small yourself to learn the tool; download big to save hours of Java
runtime.

**Rejected: MIMIC-IV.** The open-access demo (100 patients) **excludes free-text
clinical notes** — a detail most online guides get wrong. Real discharge
summaries require PhysioNet credentialing: free, but CITI training plus a
~1–2 week gate, and the data cannot be republished.

### Volume

Patient count is the wrong unit — Synthea generates a full lifetime per patient,
so row counts run an order of magnitude above intuition (`observations.csv`
dominates). No number is asserted here; **phase 1 measures it.** Three tiers:

- **dev** ~1k patients — fast iteration, run constantly
- **main** ~25–30k patients — the real dataset
- **scale run** — one-off, deliberately large, manual and never scheduled.
  Purpose is to watch shuffles, spills, and partition skew. This is where
  PySpark stops being theoretical.

## 5. Architecture

```
Synthea generator
      ↓
UC Volume /landing  (FHIR NDJSON + CSV, Auto Loader)
      ↓
┌─ Lakeflow Declarative Pipeline — ONE pipeline, written in SQL ─┐
│  Bronze          →  Silver              →  Gold                │
│  raw as-landed      conformed clinical      patient 360,       │
│  append only        entities, SNOMED/       readmit labels,    │
│                     LOINC/RxNorm            care gap measures  │
└────────────────────────────────────────────────────────────────┘
      ↓
MLflow + UC Model Registry  →  batch scores (gold table)
      ↓
Genie space  ·  AI/BI dashboard  ·  Streamlit app (public URL)

Airflow orchestrates the outer loop.
Unity Catalog governs every layer: column masks, row filters, PII tags,
lineage, audit.
```

### Key architectural decisions

**One pipeline, written in SQL.** Forced by the Free Edition one-pipeline limit,
and a good fit given strong SQL / no Spark. Declarative pipelines express the
medallion as SQL streaming tables and materialized views; the engine handles
incremental logic. PySpark appears only where SQL genuinely can't reach.

**Streamlit reads a materialized snapshot, not the warehouse.** Pointing
Streamlit at the SQL warehouse means every visitor wakes the warehouse and burns
quota — a crawler or a recruiter at 2am could contribute to killing the
workspace for the day. The pipeline writes a Parquet/DuckDB snapshot at the end
of each run; Streamlit reads that. Zero per-visitor cost, instant loads, and the
app survives throttling. Keep a live-query toggle behind a button for demos.

**Airflow sits above Databricks, not inside it.** Do not rebuild the medallion
as Airflow tasks. Airflow owns the outer loop: generate a Synthea batch, land
it, trigger the Databricks job, poll, gate on data quality, trigger retraining
on drift. Runs locally in Docker Compose with the Databricks provider.

**Airflow enters early and thin.** A DAG that just triggers a Databricks job is
~30 minutes with the provider. Introduced in phase 2, then grows every phase
(sensors, quality gates, branching, backfills, retraining triggers). Late-and-
thick maximizes the chance it never happens.

**Deploy in phase 1, not at the end.** An ugly Streamlit page and dashboard go
live in week one showing nothing but bronze row counts. Every later phase then
improves something that already has a URL. If the project stops at phase 4,
there is still a live artifact.

**Small data on purpose.** The learning is identical at 30k patients; the
failure mode is not.

## 6. SQL vs. PySpark — the comparison track

The user wants first-hand comparison. Implementing the medallion twice would
double the work *and* the copies would drift. Bounded version:

- **The SQL Lakeflow pipeline is the one production artifact.** Single source of
  truth.
- **PySpark track A — where SQL is genuinely bad.** FHIR bundle flattening
  (nested arrays, `explode`, struct navigation), PII hashing UDFs, ML feature
  assembly. Not duplication; SQL is legitimately awkward here.
- **PySpark track B — exactly 2 deliberate head-to-heads.** Not "2 or 3." Two.
  Pick where the comparison teaches most: readmission-window logic (SQL window
  functions vs. the `Window` API) and one wide aggregation.
- **The reconciliation notebook.** Runs both, diffs row-for-row, asserts
  equality, captures query plans and runtimes side by side.

The reconciliation notebook is the payoff: "I built it two ways and proved they
agree" is a stronger interview artifact than either implementation, and reading
`EXPLAIN` output is the most useful Spark skill.

## 7. dbt — scoped, and labelled as cut #1

dbt and Lakeflow Declarative Pipelines are **alternatives, not layers.** Both
build a DAG of SQL models with incremental logic, tests, and lineage. Stacking
them means maintaining the medallion twice for no learning gain.

Decision: **Lakeflow is the spine; dbt gets the gold layer only, later.**

- Gold is where dbt genuinely wins — `dbt test` on business logic, `dbt docs`,
  exposures pointing at dashboards, metrics defined once.
- It gives Airflow a real DAG. Via the Cosmos provider each dbt model renders as
  its own Airflow task, instead of Airflow poking a single opaque job.

Honest caveat recorded deliberately: the second reason is real but **not
load-bearing** — Airflow gets a meaty DAG from quality gates, backfills, and
conditional retraining regardless. The genuine case for dbt is resume value plus
a real gold-layer fit. **dbt is the first thing to cut if energy flags.** Nothing
upstream depends on it.

dbt Core is free and runs locally against the SQL warehouse.

## 8. The AI/ML position — the most important decision here

### The problem

Synthea generates patients from **explicit rule-based disease modules.** A
supervised model trained on it learns the generator's rules, not clinical
reality. Two consequences:

- A suspiciously high AUC is *worse* than a mediocre one. "0.94" followed by "on
  rule-generated synthetic data" is a bad interview moment.
- Synthea does not specifically model readmission as a phenomenon, so the base
  rate may be too low or too deterministic to be a real learning problem.

### The resolution

What is untrustworthy is **supervised prediction**, not AI in general. So the
AI centerpiece moves to somewhere synthetic data is an *advantage*:

**PHI de-identification with a ground-truth answer key.** Synthea writes
free-text clinical notes containing the generated name, address, dates, and MRN
— and `patients.csv` records exactly what those values were. That is **labeled
data.** Real de-identification projects cannot measure themselves because nobody
has annotated ground truth at scale; this is the central pain of the field.

Phase 3 therefore becomes:

- **Structural PHI** — Unity Catalog column masks, row filters, governance tags
- **Unstructured PHI** — NER over clinical notes for the 18 HIPAA Safe Harbor
  identifiers
- **Measured** — precision/recall/F1 per PHI category against the answer key,
  tracked in MLflow across model versions
- **Re-identification risk** — k-anonymity on the de-identified output, the check
  that de-ID projects routinely skip

This is not new scope. It is *different* scope inside a phase that already
existed.

### AI runs through the project, it is not a phase

| Phase | AI in it | Trustworthy on synthetic data? |
|---|---|---|
| 2 — Silver | Embedding-based mapping of local codes → SNOMED/LOINC/RxNorm | Yes — terminology is real regardless of patient |
| 3 — Governance | **PHI de-identification, F1 vs. ground truth** | **Yes — Synthea supplies the labels** |
| 5 — Analytics | Genie + text-to-SQL with a self-built eval harness | Yes — measures the interface, not the patient |
| 6 — ML | Readmission model, framed as ML engineering | Caveated, and said out loud |

The ML phase's deliverable is **ML engineering craft** — leakage-free temporal
splits, feature engineering, MLflow, registry, batch scoring, drift monitoring —
with an explicit statement that absolute performance on synthetic data is
meaningless. That is a senior answer most portfolio projects cannot give.

**Corollary:** analytics precedes ML in the phase order. On this data the
analytics are trustworthy and the predictions are not. Synthea models care
processes deliberately, so quality measures and care gaps are computed from real
logic rather than predicted from noise.

## 9. Phase order

| # | Phase | Ships |
|---|---|---|
| 1 | Calibrate + land + **deploy ugly** | Live URL day one. Row counts measured. **Readmission base-rate gate.** |
| 2 | Silver clinical model + **thin Airflow DAG** | Conformed EHR tables, terminology mapping, first DAG |
| 3 | PII governance + **de-identification AI** | UC masks/filters/tags, NER, F1 vs. ground truth, k-anonymity |
| 4 | Gold + PySpark track + reconciliation | Business tables, the diff notebook |
| — | **spec boundary — re-plan from here** | |
| 5 | Analytics | Metrics layer, AI/BI dashboard, Genie + eval harness |
| 6 | ML | MLflow, registry, batch scoring, drift |
| 7 | dbt (gold only) | Tests, docs, exposures — *cut #1* |
| 8 | Airflow depth | Cosmos, quality gates, backfills, retraining triggers |

**Only phases 1–4 get a detailed spec now.** Writing a detailed ML spec before
seeing real feature distributions is fiction; same for dashboards before knowing
what is in gold.

### Phase 1 decision gate

Measure the actual 30-day readmission base rate and class balance **before**
committing to it as the ML target. If degenerate, pivot the target
(cost/utilization, or care-gap prediction) rather than discovering it in phase 6.

## 10. Explicitly cut

- **Real-time model serving endpoint** — batch scoring into a gold table feeds
  the dashboard and app identically. Costs quota, adds ops surface. Add later in
  an afternoon if an interviewer asks.
- **Databricks App** — same Streamlit code deployed twice, sits behind workspace
  auth so it cannot be shared publicly, and auto-stops every 24h. Deploy the
  same code as an App on demand for a screen-share.
- **PySpark head-to-head beyond 2 tables.**

## 11. The scope rule

Adopted deliberately, because the real risk to this project is scope, not any
technical decision:

> **Nothing enters the plan without something leaving.**

Eight phases, no deadline, depth-first, and four comparison axes is the shape
that dies at phase 4. This rule is what keeps it alive.

## 12. Open questions

- Exact Synthea row counts and byte sizes — resolved by phase 1 calibration.
- Readmission base rate viability — phase 1 decision gate.
- Which NER approach for de-identification (rules baseline → clinical NER model
  → LLM via Foundation Model APIs) — decide in the phase 3 spec, but ship a
  regex/rules baseline first so there is a number to beat.
- Final choice of the 2 PySpark head-to-head tables — decide in the phase 4 spec.

## 13. Next step

Write the spec for phases 1–4 → `docs/specs/`.
