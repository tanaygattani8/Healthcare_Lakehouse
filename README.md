# healthcare-lakehouse

Healthcare data engineering + AI on Databricks Free Edition.

Synthetic EHR data (Synthea) → medallion lakehouse → governed PHI layer →
analytics → ML. Orchestrated with Airflow, deployed as a public Streamlit app.

**Live:** https://healthcarelakehouse.streamlit.app/

**Status:** Phase 1 complete — bronze landed, calibration measured, readmission
gate decided.

## What phase 1 produced

| | |
|---|---:|
| Patients generated | 1,148 |
| Rows landed in bronze | 3,277,048 |
| Bronze streaming tables | 12 |
| CSV on disk → Parquet | 631 MB → 47 MB |
| 30-day readmission base rate | 15.97% |

Row counts were measured locally with DuckDB before upload and re-measured in
the lakehouse afterwards. They agree entity by entity, to the row.

The readmission gate ([docs/readmission-gate.md](docs/readmission-gate.md))
existed to answer one question before any ML work was planned: does this
dataset contain a learnable target? 1,265 index admissions after excluding
in-hospital deaths and insufficient follow-up, 202 readmissions. Verdict:
proceed.

## Documents

- [Brainstorm log](docs/brainstorm-log.md) — decisions and the reasoning behind them
- [Spec: phases 1–4](docs/specs/2026-08-07-phases-1-4-design.md)
- [Calibration](docs/calibration.md) — measured dataset size
- [Readmission gate](docs/readmission-gate.md) — is the ML target viable
- [Decision log](docs/decision.md) — why each implementation went the way it did
- [Execution flow](docs/flow.md) — entry points and call order
- [Error log](docs/errors.md) — every failure hit, its symptom and its fix

## Running it

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
ruff check .
```

Talking to Databricks needs credentials: copy `.env.example` to `.env` and fill
it in. `.env` is gitignored.

Regenerating the dataset, deploying the pipeline, and publishing the snapshot
are documented in [synthea/README.md](synthea/README.md) and the phase 1 plan.

## Architecture notes

- **Bronze does nothing.** No casting, no cleaning, no dedup. Every column
  lands as a string. Bronze exists so silver and gold can be rebuilt without
  re-uploading 631 MB.
- **One pipeline, all layers.** Free Edition permits one active pipeline per
  type, so bronze/silver/gold share a single Lakeflow Declarative Pipeline.
- **The app never queries the warehouse.** A publish step writes an
  aggregate-only Parquet snapshot to `snapshots/`, it is committed, and
  Streamlit reads that file. Per-visitor queries would wake serverless compute
  and burn the daily quota — a crawler could take the workspace down for a day.
  Snapshots are aggregates only, never row-level.
- **The data is synthetic.** Synthea output, no real patient information.

## Known Free Edition degradations

Documented rather than hidden. Knowing the gap is worth more than pretending
there is none.

| Constraint | Production would do | What this project does |
|---|---|---|
| One workspace per account | Separate dev and prod workspaces | Separate catalogs, `healthcare_dev` and `healthcare`, in one workspace |
| Service principals for CI | Service principal with scoped permissions | A PAT in GitHub Actions secrets. OIDC is the upgrade path |
| Bundle `mode: production` | Enabled, enforcing run-as and deployment rules | Omitted — its `run_as` requirements cannot be met by a single-user Free Edition account |
| One active pipeline per type | A pipeline per medallion layer | One pipeline containing all layers |
| Quota shuts down compute daily | Autoscaling production clusters | Dev tier of ~1,000 patients; large runs are manual and deliberate |
| Databricks Apps for internal hosting | An App behind workspace SSO | Streamlit Community Cloud — Apps sit behind workspace auth and stop after 24h |

## Scope rule

> Nothing enters the plan without something leaving.
