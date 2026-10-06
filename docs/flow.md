# Execution flow

How execution actually travels through this codebase: entry points, what calls
what, in what order, and what changed each cycle.

**Scope.** Mechanics only. *Why* a thing is built the way it is belongs in
[decision.md](decision.md); a broken thing and its fix belong in
[errors.md](errors.md); *what* is being built belongs in the spec. If an entry
here starts explaining a tradeoff, it is in the wrong file.

**Current state: phase 1, Tasks 1–6 of 10.** Tasks 1–4 run entirely on the
laptop. Task 5 opens a connection to Databricks and Task 6 pushes data across
it — see cycles 6 and 7 at the bottom for the two entry points that added.

---

## The shape of the thing

Two independent command-line scripts. Neither imports the other, neither shares
state with the other, and both follow the same four-step shape:

```
argparse  →  DuckDB reads CSV  →  pure functions compute  →  markdown written to docs/
```

That shape is not incidental. The measurement functions are pure — they take a
connection and a path and return a dict — which is why they are testable against
tiny fixture CSVs in `tmp_path` without any Synthea data present. `main()` is the
only impure part of either file: it parses arguments, walks the filesystem and
writes.

---

## Entry point 1 — `scripts/calibrate.py`

**Invoked as:** `python -m scripts.calibrate`
**Reads:** `synthea/output/csv/*.csv`, `synthea/output/notes/`
**Writes:** `docs/calibration.md`
**Answers:** how big is this dataset, and how big does it get at 30k patients?

### Call order

```
__main__
└── main()
    ├── argparse                     --output-dir (default synthea/output)
    │                                --report     (default docs/calibration.md)
    ├── duckdb.connect()             in-memory, no file
    ├── tempfile.TemporaryDirectory()   scratch space for Parquet probes
    │
    ├── for entity in ENTITIES:      ← imported from scripts/entities.py, 12 names
    │   │
    │   ├── skip if the CSV is absent (prints "skipping …")
    │   ├── measure_file(con, path)          → {file, rows, bytes}
    │   ├── parquet_bytes(con, path, tmp)    → int      (adds "parquet_bytes")
    │   └── distinct_codes(con, path)        → int      (adds "distinct_codes")
    │                                          appends the dict to `rows`
    │
    ├── SystemExit if `rows` is empty        ← guard, see decision.md D12
    ├── patient_count ← the "rows" value of the patients.csv entry
    ├── note_stats(notes_dir)         → {note_count, total_bytes, mean_chars, max_chars}
    ├── render_markdown(rows, patient_count, notes)  → str
    └── write the string, print "wrote …"
```

The temporary directory closes when the `with` block exits, which is *before*
the guard and the report are reached — the Parquet probe files are scratch and
nothing later needs them.

### What each function does mechanically

| Function | Mechanism |
|---|---|
| `measure_file` | `SELECT count(*) FROM read_csv_auto($1)` for rows; `path.stat().st_size` for bytes. The file is never loaded into Python. |
| `parquet_bytes` | `con.read_csv(...).write_parquet(...)` into the temp dir, then `stat()` the result. Relation API, not `COPY ... TO`. |
| `distinct_codes` | Probes column names with a `LIMIT 0` query and reads `.description`. Returns `0` if `CODE` is absent, else `COUNT(DISTINCT CODE)`. |
| `note_stats` | Pure Python, no DuckDB. Lists files, reads each one, keeps only its length. One file resident at a time. |
| `render_markdown` | Pure string building. Sorts rows by descending row count, divides by `patient_count` for the extrapolation column. |

---

## Entry point 2 — `scripts/readmission_gate.py`

**Invoked as:** `python -m scripts.readmission_gate`
**Reads:** `synthea/output/csv/encounters.csv`, `synthea/output/csv/patients.csv`
**Writes:** `docs/readmission-gate.md`
**Answers:** is 30-day readmission a viable ML target on this data?

### Call order

```
__main__
└── main()
    ├── argparse                     --output-dir, --report, --window-days (default 30)
    ├── duckdb.connect()
    ├── compute_gate(con, encounters, patients, window_days)   → dict of 6 keys
    ├── SystemExit if inpatient_encounters == 0                ← guard, D12
    ├── render_markdown(result, window_days)  → str
    │   └── verdict(result)          → str, called from inside render_markdown
    └── write the string, print 3 numbers + "wrote …"
```

`verdict()` is never called by `main()` directly. It is called once, from inside
`render_markdown`, and its return value is interpolated into the report body.
The tests call it directly, which is why it must stay a standalone function.

### Inside `compute_gate` — one SQL statement, five CTEs

All the healthcare logic lives in `GATE_SQL`. Python does one thing afterwards:
divide to get the base rate, guarding against division by zero.

```
inp        filter ENCOUNTERCLASS = 'inpatient', cast START/STOP to TIMESTAMP
  ↓
bounds     max(discharged) across everything → data_end
  ↓
sequenced  LEAD(admitted) OVER (PARTITION BY patient_id ORDER BY admitted)
  ↓          → next_admitted   ← the known-limited step, decision.md D13
deaths     patient_id → death_date from patients.csv (TRY_CAST, nulls tolerated)
  ↓
flagged    CROSS JOIN bounds, LEFT JOIN deaths, compute three booleans per row:
  ↓            died_at_index    death_date <= discharge date
  ↓            short_followup   data_end - discharged < window
  ↓            readmitted       0 < (next_admitted - discharged) <= window
  ↓
SELECT     five counts, using FILTER (WHERE …) over the three booleans
```

The exclusions are **counted, not deleted** — `flagged` keeps every inpatient
encounter and the final `SELECT` partitions them with `FILTER`. That is what
makes the report able to show *why* encounters dropped out rather than only
showing the survivors.

`excluded_death` and `excluded_short_followup` are disjoint by construction:
the short-follow-up filter carries `AND NOT died_at_index`, so an encounter that
is both is counted once, under death.

### Parameter binding

`compute_gate` passes a dict — `{"enc": ..., "pat": ..., "window": ...}` — bound
to the named `$enc`, `$pat`, `$window` placeholders. The two paths are converted
with `str()` because DuckDB will not accept a `Path`.

---

## Shared module

`scripts/entities.py` exports one name, `ENTITIES`, a list of 12 strings. Only
`calibrate.py` imports it today. `pipelines/medallion/bronze/bronze.py` will
carry its own copy rather than importing it.

`scripts/readmission_gate.py` does **not** use it — the gate reads exactly two
named files.

---

## Test flow

```
pytest                        rootdir = repo root
  │
  ├── tests/__init__.py exists → pytest inserts the repo root on sys.path
  │                              → `from scripts.calibrate import …` resolves
  │                              → `scripts/` needs no __init__.py (namespace package)
  │
  ├── @pytest.fixture con      a fresh in-memory DuckDB per test
  ├── tmp_path                 pytest builtin, a fresh directory per test
  │
  ├── tests/test_calibrate.py         8 tests
  └── tests/test_readmission_gate.py  11 tests   (9 planned + 2 added, D14)
                                                  its `write()` helper builds a
                                                  fixture encounters.csv and
                                                  patients.csv from string bodies
```

19 tests total. No test touches `synthea/output/` — every one builds its own
CSVs, which is why the suite runs in about two seconds and works on a machine
that has never run Synthea.

Nothing calls `main()` in either script. Both `main()` functions are untested
by construction; the guard added in D12 is the only logic in them and it is
verified by hand.

---

## Data lifecycle, end to end

```
Synthea jar  ──(synthea.properties, fixed seeds)──►  synthea/output/    [gitignored]
                                                       ├── csv/    18 files, 2.1 GB
                                                       ├── fhir/
                                                       ├── notes/  1,148 files, 384 MB
                                                       └── metadata/
                                                              │
                     ┌────────────────────────────────────────┴──────────┐
                     ▼                                                   ▼
             scripts/calibrate.py                          scripts/readmission_gate.py
                     │                                                   │
                     ▼                                                   ▼
            docs/calibration.md                            docs/readmission-gate.md
                  [committed]                                     [committed]
```

The generated data is gitignored and the reports are committed. That inversion
is the point: the dataset is reproducible from `synthea.properties` and the
seeds, so it does not need storing, while the reports are decision records that
later phases extrapolate from and must survive.

---

## Change log

### Cycle 1 — 2026-08-07/08 · Tasks 1–2 · scaffolding and data

- Added `scripts/entities.py`, `requirements.txt`, `pyproject.toml`,
  `.gitignore`, `tests/__init__.py`.
- Added `synthea/synthea.properties` and `synthea/README.md`.
- No executable flow yet — nothing had an entry point.

### Cycle 2 — 2026-08-09 · Task 3 · calibration

- **New entry point:** `python -m scripts.calibrate`.
- Added `scripts/calibrate.py` with five functions and `main()`.
- Added `tests/test_calibrate.py`, 8 tests.
- `parquet_bytes` changed from `COPY ... TO` to the relation API after a parser
  error (D9).

### Cycle 3 — 2026-08-15 · Task 3 review fixes

- `main()` gained the empty-input `SystemExit` guard (D12).
- `note_stats` return grew from 2 keys to 4: added `total_bytes`, `max_chars`
  (D11). Its two duplicated zero-returns collapsed into one guarded return.
- `render_markdown` gained a note-bytes line and an exclusion caveat.
- Test suite grew 2 asserts; no new test functions.
- Line-length fixes; `ruff check .` passes.

### Cycle 4 — 2026-08-15 · Task 4 · the gate

- **New entry point:** `python -m scripts.readmission_gate`.
- Added `scripts/readmission_gate.py`: `GATE_SQL`, `compute_gate`, `verdict`,
  `render_markdown`, `main`.
- Added `tests/test_readmission_gate.py`, 11 tests.
- `main()` carries the same guard as `calibrate.py`, keyed on
  `inpatient_encounters == 0`.
- No change to any existing file — the gate is fully independent of calibration.

### Cycle 5 — 2026-08-15 · process

- Added `docs/decision.md` and `docs/flow.md`.
- No code changed. No flow changed.

### Cycle 6 — 2026-09-02 · Task 5 · Databricks setup

- **New entry point:** `python -m scripts.run_sql <file.sql>`. Needs the venv —
  it imports `databricks.sql` from `databricks-sql-connector`.
- Added `scripts/run_sql.py`: `_statements()` splits a file naively on `;`,
  `run_file()` opens one warehouse connection and executes each statement in
  order, `main()` takes a path argument.
- Added `setup/00_catalogs.sql` — 14 statements creating two catalogs, five
  schemas each, and a `bronze.landing` volume in each.
- Auth reaches the code through `os.environ`: `DATABRICKS_HOST` (scheme
  stripped), `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`, all from `.env`.
- The Databricks CLI was installed separately and authenticates through
  `~/.databrickscfg` — a different path from the Python scripts entirely.

### Cycle 7 — 2026-09-02 · Task 6 · upload

- **New entry point:** `powershell -File scripts/upload.ps1`. Does **not** need
  the venv — no Python runs; it shells out to the `databricks` binary.
- Added `scripts/upload.ps1`. Flow: create the target directory, then loop the
  twelve entities, skipping any whose local CSV is absent, `fs cp --overwrite`
  each one, throwing on a non-zero exit.
- Result: 12 CSVs at `/Volumes/healthcare_dev/bronze/landing/csv/`, ~631 MB.
  This is what Task 7's Auto Loader will read.

**First cross-machine boundary in the project.** Everything before this ran
entirely on the laptop. From here the flow leaves the machine:

```
synthea/output/csv/   ──upload.ps1──►   /Volumes/healthcare_dev/bronze/landing/csv/
   [local, gitignored]                        [Unity Catalog volume]
                                                        │
                                                        ▼
                                            Task 7: Auto Loader → bronze
```

`scripts/entities.py` now has its list duplicated in two places — `upload.ps1`
and, from Task 7, `bronze.py`. Nothing enforces the match yet ([D21](decision.md)).

### Cycle 8 — 2026-09-02 · process

- Added `docs/errors.md`, backfilled E1–E15 covering Tasks 1–6.
- No code changed. No flow changed.

## Entry point 3 — the bronze pipeline (runs on Databricks)

**Invoked as:** `databricks bundle deploy -t dev` then `databricks bundle run medallion -t dev`
**Reads:** `/Volumes/healthcare_dev/bronze/landing/csv/<entity>/`
**Writes:** twelve streaming tables `healthcare_dev.bronze.br_<entity>`

Unlike entry points 1 and 2, no `main()` runs. Lakeflow **imports** `bronze.py`,
and the import itself registers the tables:

```
databricks bundle run
└── Lakeflow reads databricks.yml
    ├── serverless: true, catalog/schema from the target's variables
    ├── configuration → spark.conf: landing_path, batch_id
    └── imports pipelines/medallion/bronze/bronze.py
        │
        ├── LANDING_PATH = spark.conf.get("landing_path")
        │
        └── for _entity in ENTITIES:          ← its own copy of the 12 names
            └── make_bronze_table(entity)
                └── @dlt.table(name=f"br_{entity}")   ← registers, does not run
                    def _bronze():
                        readStream.format("cloudFiles")
                          .option(schemaLocation → _schema/{entity})
                          .load(csv/{entity}/)         ← directory, not file
                          .select("*", _source_file, _ingested_at, _batch_id)
        │
        └── Lakeflow resolves all 12 flows, then executes them in parallel
```

`make_bronze_table` is a function rather than a bare loop body for one reason:
a loop body closes over the loop variable, so all twelve `@dlt.table`
definitions would resolve `entity` to `payers` at execution time and every table
would read the same file. The function gives each closure its own binding.

The three `_` columns are the only thing bronze adds. No casting, no cleaning —
`cloudFiles.inferColumnTypes=false` lands every column as a string.

### Cycle 9 — 2026-09-05 · Task 7 · bronze

- **New entry point** as above. First code in the project that does not run on
  the laptop.
- Added `pipelines/medallion/bronze/bronze.py` and `databricks.yml`.
- Landing layout changed to one directory per entity ([D22](decision.md)); the
  volume was restructured server-side and `upload.ps1` updated to match.
- Added `tests/test_entity_lists_match.py`, 2 tests — the three-way list sync
  [D21](decision.md) deferred until `bronze.py` existed. Suite is now 21.
- **Verified end to end:** all twelve `br_*` tables hold exactly the row counts
  `docs/calibration.md` measured locally in DuckDB — 3,277,048 rows total. The
  local measurement and the lakehouse agree to the row.

```
synthea/output/csv/     ──upload.ps1──►  landing/csv/<entity>/<entity>.csv
   [local, gitignored]                            │
                                                  ▼  Auto Loader
                                       healthcare_dev.bronze.br_<entity>
                                            12 streaming tables
```

### Cycle 10 — 2026-09-06 · Task 8 · snapshot publish

- **New entry point:** `python -m scripts.publish_snapshot`. Needs the venv.
- Added `scripts/dbx.py`. Every warehouse connection now goes through
  `dbx.connect()`, which calls `load_dotenv()` first — previously nothing loaded
  `.env` at all and the scripts depended on shell state ([E21](errors.md)).
- `run_sql.py` rewritten onto it; its duplicated `sql.connect(...)` block is gone.
- `publish_snapshot.py`: `build_count_query()` builds one `UNION ALL` over the
  twelve bronze tables, `fetch_counts()` runs it and stamps `captured_at`,
  `main()` writes `snapshots/bronze_counts.parquet`.

```
python -m scripts.publish_snapshot
└── main()
    ├── fetch_counts(catalog, ENTITIES)
    │   ├── dbx.connect()            ← load_dotenv, validate, sql.connect
    │   ├── build_count_query(...)   ← 12 SELECTs joined by UNION ALL
    │   └── DataFrame + captured_at (UTC)
    └── to_parquet("snapshots/bronze_counts.parquet")
```

**The point of this task.** The snapshot is committed to the repo, and the
Streamlit app reads the Parquet file. The app never opens a warehouse
connection, so no visitor — or crawler — can wake serverless compute. One
warehouse query happens when *you* run this script, deliberately.

Aggregates only, never row-level: twelve rows of entity and count.

## Entry point 4 — the Airflow DAG (runs on the laptop, drives Databricks)

**Invoked as:** trigger `medallion` at http://localhost:8080, or
`docker compose --env-file ../.env exec airflow-scheduler airflow dags trigger medallion`
from `orchestration/`. Never on a schedule (`schedule=None`).
**Reads:** the root `.env` (via compose), `MEDALLION_PIPELINE_ID`
**Writes:** nothing itself — it starts one pipeline update

```
docker compose --env-file ../.env up -d          (orchestration/)
└── compose builds AIRFLOW_CONN_DATABRICKS_DEFAULT from DATABRICKS_HOST/TOKEN  (D37)
    └── scheduler (LocalExecutor, D38) parses dags/medallion.py
        └── trigger → run_medallion: DatabricksSubmitRunOperator
            ├── POST /api/2.1/jobs/runs/submit
            │     tasks=[{task_key: medallion, pipeline_task: {pipeline_id}}]
            │     └── Databricks starts ONE update of medallion-dev   (cause JOB_TASK)
            │         └── on failure the pipeline retries itself (RETRY_ON_FAILURE)
            └── polls runs/get until a terminal state
                ├── SUCCESS           → task green
                └── FAILED / INTERNAL → task red   (retries=0: no second round)
```

Afterwards, by hand: `python -m scripts.publish_snapshot`, commit, push (D36).

## Entry point 5 — the Synthea image (regenerates the dataset)

**Invoked as:** `docker build -t healthcare-synthea:7e08387 synthea/` then
`docker run --rm -v C:\synthea-test:/data healthcare-synthea:7e08387`
**Writes:** `/data/synthea/output/{csv,fhir,notes,metadata}` — a scratch mount,
never `synthea/output/`

```
docker build
├── stage 1 (eclipse-temurin:17-jdk)
│   ├── git fetch --depth 1 origin 7e08387…          ← one commit, not the history
│   ├── git describe → src/main/resources/version.txt ← else Build-Version: N/A (E29)
│   └── ./gradlew uberJar → synthea-with-dependencies.jar
└── stage 2 (eclipse-temurin:21-jre)  jar + synthea.properties only
docker run
└── java -Duser.timezone=America/Chicago -Xmx3g -jar synthea.jar -c synthea.properties
         -p 1000 -s 12345 -cs 12345 -r 20260101 -e 20260808 Massachusetts
```

Reproduces the recorded dataset to 0.004% (132 rows of 3.28 million, all near
the cutoff); bytes differ by line endings — D35.

**Batch 2 (D65):** the same jar, `-p 10000 -s 67890 -cs 12345`, CSV only, into
`synthea/output_b2/`. Then `python -m scripts.new_reference_rows synthea/output
synthea/output_b2` (only new hospitals, doctors and payers), then
`upload.ps1 -OutputDir synthea/output_b2 -Suffix b2`, then one normal pipeline
update. Command in `synthea/README.md`.

### Cycle 11 — 2026-09-18 · Phase 2b · orchestration and reproducibility

- **Two new entry points** as above; the second is the first entry point that
  needs Docker.
- `databricks jobs submit` proved the `runs/submit` + `pipeline_task` route
  before Airflow existed (D33).
- `--validate-only` adopted as the SQL check, proven on 2a's real parse bug
  (D34); the rule is in the README.
- Airflow 3.3.2 in `orchestration/`, provider `apache-airflow-providers-databricks==7.20.0`.
  DAG proven green on a good pipeline, **red on a broken one**, green again.
- Synthea image built and run five times. Causes found in turn: heap size,
  end date, timezone. Final run: 1,148 patients, 132 rows of 3.28 million
  different (D35).
- Errors E25–E32. Three of them silent (E29, E30, E31).

---

## Entry point 6 — the governance SQL (runs against Unity Catalog)

Six files in `sql/`, each run with
`.venv/Scripts/python.exe -m scripts.run_sql sql/<file>`. Order matters: a
policy cannot compile before the tag it matches exists, and a tagged column
without a policy is an unprotected PHI column.

```
governed_tag_fix.sql      CREATE GOVERNED TAG phi_category, 8 values
        │                 account-level; ABAC matches only governed tags (E35)
        ▼
governance_bootstrap.sql  ops.phi_clearance, is_cleared(),
        │                 mask_text / mask_zip / mask_date / mask_point
        ▼
governance_tags.sql       19 columns on silver.patient
        │                 STATE and patient_id deliberately excluded (D44)
        ▼
governance_policies.sql   4 COLUMN MASK policies ON SCHEMA silver
        │                 attached to the schema, not the view, so a full
        │                 refresh cannot drop them (D43)
        ▼
governance_quarantine.sql same 19 tags + same 4 policies on ops
        │                 quarantine holds whole failed rows, PHI included
        ▼
governance_row_filter.sql row_scope tag, filter_state(), 1 ROW FILTER policy
                          registering the tag and creating the policy in one
                          run fails the first time (E36)
```

Then, independently:

- `governance_check.sql` — the drift check. Run **after every pipeline full
  refresh**. Check 1 returns nothing when correct; check 2 must read 19 and 19.
- `governance_verify.sql` — flips the clearance row and shows the masks
  opening and closing. Leaves clearance restored.
- `governance_audit.sql` — creates `ops.phi_access_audit` over
  `system.query.history`.

**Before any gold build, read `ops.phi_clearance`.** The policies apply to the
identity the pipeline runs as: no clearance row fills gold with `***`, and a
wrong `scope_state` makes gold empty. Neither raises an error (D47).

### Cycle 12 — 2026-09-23 · Phase 3a · structural PHI governance

- **Probes first.** Five mechanisms tested before any were planned around; two
  of three predictions were wrong (D41). ABAC found only by reading
  `information_schema` (D42), which replaced the whole design (D43).
- Masks are **schema policies matching governed tags**, not MASK clauses on
  columns. `patient.sql` is untouched by governance.
- Nineteen columns tagged in each of two schemas, nine policies, one audit view.
- **The full refresh was survived**: tags intact, masking intact — the design's
  last open risk.
- Errors E34–E38. Two of them silent, both in the governance layer itself: a
  drift check that would have passed for ever (E37) and a function the file and
  the catalog disagreed about (E38).

### Cycle 13 — 2026-09-24 · Phase 3b steps 0–3 · notes in, answer sheet built

- **Notes landed** as `bronze.br_notes` (1,148 rows, one per patient) and cut
  into 214,238 overlapping pieces in `silver.note_chunk`; every note rebuilds
  exactly from its pieces.
- **Test set fixed before any program ran**: `ops.heldout_patient`, 25
  patients, 5,263 pieces — cut from 200 by NER cost on CPU (D51).
- **The answer sheet is built locally**, because it needs the note text and the
  patient details matched by exact search:
  `synthea/output/notes` + `silver.patient` + `silver.encounter` →
  `scripts/build_answer_key.py` → `data/phi_span.csv` (gitignored, holds real
  names) → landing volume → `sql/phi_span.sql` → `silver.phi_span`,
  `surface_text` masked by the silver schema policy.
- Errors E39–E42. Three were in the answer sheet and none raised anything: a
  10-hour search (E40), a filter dropping real names (E41), duplicate rows
  (E42). Any of them would have moved every score in the phase.

### Cycle 14 — 2026-09-24/25 · Phase 3b steps 4-8 · detect, mark, de-identify, publish

- **Four programs**, all writing `ops.detection_span` for the 25 test
  patients: roster (SQL), patterns (`scripts/detect_regex.py`), name model
  (`scripts/detect_ner.py`, laptop, after Databricks' cap stopped it, E44),
  language model (`scripts/detect_llm.py`, one `ai_query` statement per
  patient, replies kept in `ops.llm_reply`). Laptop CSVs reach the table via
  the landing volume and `sql/load_detections.sql`.
- **Marking**: `sql/score_detection.sql` -> `ops.detection_score`, rewritten
  after recall came out at 1.053 (E45). Logged to MLflow by
  `scripts/log_mlflow.py`.
- **De-identified copy**: `sql/deid.sql` builds `ops.deid_key` (the secret),
  the `ops.deid_text` Python function, and `deid.patient`, `deid.encounter`,
  `deid.note`. `sql/check_deid.sql` proves it. `sql/kanon.sql` ->
  `ops.kanon_spread`.
- **Published**: `scripts/publish_snapshot.py` now also writes
  `snapshots/deid_scores.parquet` and `deid_kanon.parquet`, and refuses any
  text that is not a known category. `app/pages/2_De-identification.py`.
- Errors E43-E47. The two that would have shipped wrong numbers were in the
  marking query and the model's merge step, not in any model.

### Cycle 15 — 2026-09-27 · Phase 4 probes, steps 1-2 · reference tables and the visit fact

- **Probes**: `sql/probe_phase4.sql` (P2-P5, P7) and
  `notebooks/p6_fhir_probe.py` (P6, one bundle on
  `landing/fhir_probe/`). P1 was a throwaway gold view, built once and
  dropped. Results and what they changed: decision.md D57.
- **Gold starts in the pipeline**: `pipelines/medallion/gold/dims.sql`
  (`dim_date`, `dim_organization`, `dim_provider`, `dim_payer`, from bronze)
  and `fact_encounter.sql`, both listed in `databricks.yml` and built with
  `refresh_selection`, never a full refresh.
- **Checks**: `sql/check_gold.sql`, which grows each step and is rerun whole.
- **Readmissions** (step 3): `planned_reason.sql` then
  `readmission_events.sql`. Proven against a rerun of the phase 1 gate
  (`scripts.readmission_gate --report data/readmission-gate-today.md`, never
  the default report path, which is the committed phase 1 record);
  `sql/readmission_ladder.sql` accounts for the rate change (D58).
- **Care gaps** (step 4): `measure_code.sql` (every code, one place) then
  `care_gap.sql`, for the last complete year (D59).
- **One row per patient** (step 5): `patient_360.sql`, built last because it
  reads `fact_encounter`, `measure_code` and `readmission_events` (D60).
  Then `sql/governance_check.sql`.
- **FHIR, track A** (step 6): 25 bundles staged to `data/fhir_sample/<patient_id>.json`
  (gitignored), uploaded to `landing/fhir/`, then `notebooks/fhir_flatten.py`
  run as a job -> `ops.fhir_encounter`, `ops.fhir_condition` (D61).
- **PySpark, track B** (step 7): `notebooks/gold_pyspark.py` as a job ->
  `ops.pyspark_readmission_events`, `ops.pyspark_patient_360`. Reads
  `gold.planned_reason`, `gold.fact_encounter` and `gold.measure_code`, so it
  runs after the pipeline has built them.
- **Reconciliation** (step 8): `sql/reconciliation_results.sql` once, then
  `notebooks/reconcile_gold.py` as a job, appending to
  `ops.reconciliation_results` (D62).
- **App** (step 9): `python -m scripts.publish_snapshot` also writes
  `snapshots/gold_readmission.parquet` and `gold_care_gap.parquet`, read by
  `app/pages/3_Quality_measures.py` (D63).

**Entry points for gold, in order:** `databricks bundle deploy -t dev`, then
`pipelines start-update --json '{"refresh_selection": [...]}'` table by table
(dims, fact_encounter, planned_reason + planned_procedure + readmission_events,
measure_code + care_gap, patient_360), then `sql/check_gold.sql`, then the two notebooks,
then `scripts.publish_snapshot`.

### Cycle 16 — 2026-09-30 to 10-03 · Phase 5 · the readmission story and text-to-SQL

1. **Probes**: `sql/probe_phase5.sql` (P1 metric views, P3 `ai_query` and
   billing) and `scripts/probe_genie.py` (P2), with a throwaway Genie space.
2. **`gold.readmission_signals`** (and `planned_procedure`, D64/D68): listed
   in `databricks.yml`, `bundle deploy -t dev`, a `--validate-only` update
   **left to finish**, then `refresh_selection` on
   `planned_procedure, readmission_events, readmission_signals, patient_360`.
   Then `notebooks/gold_pyspark.py` and `notebooks/reconcile_gold.py` as jobs
   (upload with `MSYS_NO_PATHCONV=1`, E51), and `sql/readmission_ladder.sql`.
3. **`sql/check_gold.sql`**: every `_must_be_0` is 0, and 10,724 / 140.
4. **The question sets**: `eval/questions_dev.yaml` (Claude), then
   `eval/questions_test.yaml` (the user), frozen into
   `eval/questions_test.sha256` and committed **before** step 5.
5. **`sql/metric_views.sql`** (laptop SQL, `scripts.run_sql`) creates
   `healthcare_dev.metrics.stays` and `.readmission`; then
   `sql/check_metrics.sql`.
6. **The harness**: `python -m scripts.eval_text_to_sql --set dev|test
   --run-id dev-N|test-N --contestants answer_key,raw,metrics,genie
   --genie-space <id>`, resumable, writing verdicts to `ops.eval_run`; then
   `sql/eval_report.sql` (it prints at most 20 failure rows).
7. **`python -m scripts.publish_snapshot`** writes `story_totals`,
   `story_levels` (small cells hidden, D66), `story_verdict` and
   `eval_scores`, and no longer `gold_readmission`.
8. **App page 4**, `app/pages/4_Readmission_story.py`, reads those four
   files; page 3 keeps care gaps and links to it.

The story's rule (`scripts/readmission_story.py`) is pure Python with its
own tests; `publish_snapshot` calls it, so the app does no statistics.

### Cycle 17 — 2026-10-03/04 · Phase 6 · the readmission model

1. **Probes**: `sql/probe_phase6.sql` (the `ml` schema, P3, P4) and
   `notebooks/probe_ml.py` (P1 versions, P2 Unity Catalog registry).
2. **`gold.readmission_signals`** gains `admit_day`, `discharge_day`,
   `had_bypass_surgery`, `days_since_last_discharge`, `encounters_in_stay`,
   `arrived_via_emergency`: `bundle deploy -t dev`, `--validate-only` left to
   finish, then `refresh_selection` on `gold.readmission_signals` only. Then
   `sql/check_gold.sql` (10,724 / 140 and 9,891 / 61). `readmission_events`
   did not change, so no PySpark reconcile.
3. **Every notebook runs the same way**: `databricks bundle deploy -t dev`
   uploads `notebooks/` and `scripts/` to the bundle's `files/` folder, then
   `bash scripts/run_notebook.sh <name>` submits it as a one-off serverless
   job, waits, and prints its exit JSON. Each notebook first `%pip`-installs
   scikit-learn 1.6.1 and MLflow 3.16.1, sets the Files API switch (E52), and
   puts the `files/` folder on `sys.path`.
4. **`train_readmission`** reads `gold.readmission_signals`, and per
   population calls `split` → `cv_scores` → refit → `oof_scores` →
   `alert_threshold` (on the out-of-fold scores, D72) → `evaluate`. It logs 10 MLflow runs per population to
   `/Users/<you>/readmission`, registers `healthcare_dev.ml.readmission_all`
   and `..._no_bypass` with alias `champion` and tags, and overwrites
   `ml.model_results`.
5. **`score_readmission`** loads each `@champion`, checks the production
   count against the `prod_stays` tag, and replaces that version's rows in
   `ml.readmission_scores`.
6. **`drift_readmission`** loads both champions and appends one batch to
   `ml.drift_report` (`drift_report` for features, PSI for scores against
   out-of-fold training scores, Wilson for flag and readmission rates), plus
   an MLflow run tagged `drift`.
7. **`python -m scripts.publish_snapshot`** now also writes
   `model_results` (counts dropped, small recalls hidden, breakdowns as a
   verdict only, rounded) and `model_drift` (the latest run, rounded), which **app page 5**,
   `app/pages/5_Readmission_model.py`, reads.

The rules live in `scripts/readmission_model.py` and `scripts/drift.py`,
pure Python with their own tests; the notebooks only read, call and write.


### Cycle 18 — 2026-10-04/05 · Phase 7 · gold gates (dbt cut)

1. **Probes**: a throwaway `zz_probe_phase7.sql`, validated only, then
   removed. It covered a private view with expectations, a typed column
   list (and a planted wrong type), and a pipeline reading
   `information_schema`.
2. **Before**: `sql/gold_fingerprint.sql` (12 gold tables, row count and
   hash sum) into `data/`, and `sql/phase7_before.sql` (a copy of
   `readmission_signals` in `ops`).
3. **How a gate stops an update**: a row gate sits in its table's `CREATE`
   (`CONSTRAINT ... EXPECT ... ON VIOLATION FAIL UPDATE`) and fails the
   update before that table is replaced. A cross-table gate is a column of
   the private view `gold_checks`, one row of violation counts, and fails
   the update after the tables it reads. Either way the update reads
   `FAILED`, and `get-update`, the pipeline UI and the Airflow task show it;
   `list-pipeline-events` names the constraint and the failing row.
4. **Run**: `bundle deploy -t dev` → `--validate-only` → `refresh_selection`
   on the changed tables plus `gold_checks` (selectable by name).
5. **After**: the fingerprint again, compared with `diff` (`key_copies` is
   left out), and `sql/phase7_proof.sql`: `readmission_events` against
   the PySpark copy, `readmission_signals` against its before-copy, both
   ways. Then a planted `gold_checks` failure, restored, a clean run, and
   the copy dropped (`sql/phase7_cleanup.sql`).
6. `sql/check_gold.sql` is a report; `tests/test_gold_contract.py` checks
   that every column the model reads is declared. `reconcile_gold.py` drops
   `key_copies` before comparing.

### Cycle 19 — 2026-10-05 · Phase 8 · the operations dashboard

1. **Probes**: `sql/probe_phase8.sql` (where the data ends; a star join in
   a throwaway metric view), a parameter in a metric view's `WHERE`, the
   counter's comparison value in the UI, and the CLI's `generate` and
   `bind` commands.
2. **Before**: the gold fingerprint and the metric-view checks into
   `data/`, and `sql/phase8_before.sql` (a copy of `readmission_signals`).
3. **Gold**: stay cost and length of stay move into `readmission_events`,
   and `readmission_signals` reads them. Then `bundle deploy -t dev` and
   `refresh_selection` on the two tables plus `gold_checks`.
   `sql/phase8_proof.sql` and the fingerprint show nothing else moved.
4. **Metrics**: `sql/metric_views.sql` (`operations`, `care_gaps`, `stays`
   extended), then `sql/dashboard_support.sql` (`shown`, `kpi_window`),
   then `sql/check_metrics.sql`. The dev text-to-SQL set is rerun
   (dev-3 to dev-5, E60).
5. **Dashboard**: every dataset is run on the default view (that is where
   E61 surfaced). The page is built through the Lakeview API, then exported:
   `databricks bundle generate dashboard --existing-id <id> --key operations -s dashboards -d resources`,
   `bundle deployment bind`, `bundle deploy -t dev`.
   `tests/test_dashboard_privacy.py` reads `dashboards/operations.lvdash.json`.
6. **Changing it later**: edit the JSON and deploy, or edit in the UI and
   re-export with `--resource operations --force`. Then check
   `git diff resources/` for `parent_path` (E62) and run the privacy test.

## Entry point 7 — the retrain DAG (laptop Airflow, drives Databricks)

**Invoked as:** from `orchestration/`,
`docker compose --env-file ../.env exec airflow-scheduler airflow dags trigger retrain -c '{"as_of": "2021-01-01", "mode": "replay"}'`.
`as_of` is required and must be a date; `mode` is `replay` (default) or
`live`. Never on a schedule (`schedule=None`). One run at a time
(`max_active_runs=1`).
**Reads:** the pipeline's update list, `gold.readmission_signals`,
`ml.retrain_history`, the `readmission_all` registry.
**Writes:** one `ml.retrain_history` row, one MLflow run, and on a win a
registry version plus alias (`replay_<year>`, or `champion` when live). A
live win also rewrites that version's rows in `ml.readmission_scores`.

```
trigger retrain  (as_of, mode)       params validated at trigger: a bad date makes no run
├── gold_is_gated          @task, GET 2.0/pipelines/<id>/updates through DatabricksHook
│     ├── any update not COMPLETED/FAILED/CANCELED → red ("update <id> is RUNNING")
│     └── newest non-validate-only update not COMPLETED → red          (D73)
├── retrain                DatabricksSubmitRunOperator → notebooks/retrain_readmission
│     ├── 1. order guard   rt.order_problem: replay one year at a time from 2021;
│     │                    live needs six replays; no (as_of, mode) twice
│     ├── 2. champion      live: @champion · replay: newest replay alias, else @champion
│     ├── 3. trigger       rt.flag_rate on the 12 months before as_of vs rt.budget (21.8%)
│     │                    rt.shifted_features stored, triggers nothing
│     ├── 4. challengers   new cutoff: same model, rm.alert_threshold on the 12 months before
│     │                    retrain: rm.build_pipeline(champion's kind) on every labelled stay
│     │                    before the check window; rt.window_scores = out of fold where seen
│     ├── 5. gate          rt.on_budget (Wilson) + rt.ranking_guard (AP, patients resampled)
│     ├── 6. promote       rt.winner → copy_model_version | log_model, tags, alias
│     └── 7. history row   appended LAST; exit JSON {outcome, version, alias}
├── promoted_live          @task.short_circuit: 2.1/jobs/runs/get-output, logs the outcome
│     └── continues only if mode = live and the outcome is a promotion
└── rescore                DatabricksSubmitRunOperator → notebooks/score_readmission
                           scores from rt.scored_from(champion.tags): 2020, or after its training
```

If a task dies at `Pre Execute` with `httpx.ReadTimeout` (E32, E63), trigger
the same `as_of` again: nothing reached Databricks and no row was written.
By hand, without Airflow:
`bash scripts/run_notebook.sh retrain_readmission '{"as_of": "2021-01-01", "mode": "replay"}'`,
after checking `databricks pipelines list-updates <id>` yourself.

### Cycle 20 — 2026-10-06 · Phase 9 · retraining on drift

1. **Probes**: `notebooks/probe_retrain.py` (P1 `copy_model_version`, P5
   v2's flag rate by year, P6 the last admit day, P7 v2's settings); the
   provider's hook in the scheduler container (P2 pipeline updates, P3 a
   notebook's exit value: no `api/` prefix); a throwaway `probe_params` DAG
   (P4 typed params). E63 and E64 were met here.
2. **Rules**: `scripts/retrain.py` and `tests/test_retrain.py`;
   `rm.patient_resamples` pulled out of `bootstrap_difference`, pinned by a
   test.
3. **Before-record**: `sql/ml_fingerprint.sql` and the registry aliases.
4. **Scoring**: the `scored_from` line in `score_readmission`, then a
   rescore on v2; the fingerprint matched exactly.
5. **One cursor by hand**: `notebooks/retrain_readmission.py` and
   `sql/retrain_history.sql`; `run_notebook.sh` takes JSON parameters. 2021
   ran in 1 min 51 s and promoted v4.
6. **The DAG**: `orchestration/dags/retrain.py`; import check; the gate seen
   red during a `--validate-only` update, with no Databricks run started.
7. **Replay** 2022-2026 through Airflow, one at a time.
8. **Sandbox check, then live**: fingerprints and aliases unchanged; the
   live run (`as_of` 2026-07-15) promoted v5 to `champion` and rescored.
   The results are in D75.
