# healthcare-lakehouse

Healthcare data engineering + AI on Databricks Free Edition.

Synthetic EHR data (Synthea) → medallion lakehouse → governed PHI layer →
analytics → ML. Orchestrated with Airflow, deployed as a public Streamlit app.

**Live:** https://healthcarelakehouse.streamlit.app/

**Status:** Phase 3a complete — bronze landed, silver modelled, the pipeline
triggered from Airflow, PHI columns classified and masked. Phase 3b (the
de-identification AI) is next.

## What phase 3a produced

| | |
|---|---:|
| PHI columns classified | 19, in each of two schemas |
| Column mask policies | 8 |
| Row filter policies | 1 |
| Safe Harbor categories | 8 |

Masks are **ABAC policies attached to the schema**, matching governed tags —
not `MASK` clauses on columns. A column mask attached to `silver.patient`
would be lost the next time the pipeline recreated it, silently, which is the
worst possible failure for a security control. A schema policy is not part of
the table definition. Verified by full-refreshing `silver.patient` and
confirming the tags and the masking both survived.

Clearance is a row in `ops.phi_clearance`, so the mask can be shown opening and
closing on demand: `999-27-2324` → `***`, `01730` → `017`, `2022-11-30` →
`2022-01-01`. Safe Harbor permits the year and nothing finer, so the `01-01`
is fabricated and the column comment says so.

`sql/governance_check.sql` is the drift check: tags are what the policies match
on, so a lost tag silently unmasks a column. **Run it after every full
refresh.**

## What phase 2 produced

| | |
|---|---:|
| Silver tables | 12 |
| Quarantine tables | 9 |
| Rows quarantined, all tables | 104 |
| Orchestration | Airflow 3.3.2, five containers, `medallion` DAG |

Every silver table is built as a pair: a typed view carrying a `violations`
array, then a materialized view keeping only the rows where that array is
empty. The failing rows are not dropped — they land whole in
`ops.quarantine_<name>`, which is why the number above is known rather than
estimated. 104 of 3,277,048 rows failed a rule, all of them medications.

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

Regenerating the dataset is documented in
[synthea/README.md](synthea/README.md). Deploying the pipeline and publishing
the snapshot run from `databricks bundle deploy` and
`python -m scripts.publish_snapshot`.

Before pushing a change to pipeline SQL, check it compiles without building
anything:

```bash
databricks bundle deploy -t dev
databricks pipelines start-update <pipeline-id> --validate-only
```

Not in CI: it needs Databricks compute, and running it on every pull request
spends the daily quota whose exhaustion locks the workspace.

### Orchestration (Airflow, needs Docker Desktop)

```bash
cd orchestration
docker compose --env-file ../.env up airflow-init
docker compose --env-file ../.env up -d
```

Open http://localhost:8080 (airflow / airflow) once `docker compose ps` shows
every service `(healthy)`, and trigger the `medallion` DAG by hand. It is never
scheduled: on Free Edition a timer-driven run can exhaust the daily quota
unattended. `--env-file ../.env` is how Airflow gets the Databricks credentials —
there is no second credential file.

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
| One account, which owns every object | A service principal owns `ops`; analysts get `SELECT` on `silver` and nothing on `ops` | A row in `ops.phi_clearance`. **Separation of duties is impossible here, not merely weak** — there is one principal and it owns everything, so the masks demonstrate a mechanism and enforce nothing against their owner. A second principal is the fix; `REVOKE` is not |
| One state in the dataset | Row filters segregate by region | The filter works and is verified, but with every patient in Massachusetts it can only be all-rows or no-rows |

## Scope rule

> Nothing enters the plan without something leaving.
