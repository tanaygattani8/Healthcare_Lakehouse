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
