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
