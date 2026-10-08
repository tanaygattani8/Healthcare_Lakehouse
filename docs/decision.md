# Decision log

Every decision taken **while writing code** — the library, the API, the
approach to a bug, the shortcut accepted and its ceiling. Newest at the bottom;
append, never rewrite. If a decision here is later reversed, add a new entry
saying so rather than editing the old one — the wrong turn is the useful part.

**How this differs from the other two documents.** Keeping the boundary sharp is
what stops all three from converging into the same file:

| Document | Holds | Written when |
|---|---|---|
| `brainstorm-log.md` | Pre-implementation design decisions — what to build, what was rejected | Before code exists. Frozen. |
| `decision.md` (this) | Implementation decisions — how it was built and why that way | While writing code |
| `flow.md` | Mechanics — entry points, call order, what changed | After code changes |
| `errors.md` | Failures — the symptom verbatim, the cause, the fix | When something breaks |

`decision.md` is keyed by **choice**; `errors.md` is keyed by **symptom**. An
error that forced a choice appears in both, cross-linked.

A decision belongs here if a reasonable engineer could have chosen otherwise and
would want to know why we didn't.

---

## D1 — Backfilled entries

Entries D2–D14 were written retroactively on 2026-08-15, covering Tasks 1–4.
They are reconstructed from the code, the commits and the session that produced
them, so the reasoning is accurate but the wording is not contemporaneous.
Everything from D15 onward is written as it happens.

---

## Task 1 — Repository scaffolding

### D2 — DuckDB for all local measurement, not pandas

**Decision.** Every local measurement script reads CSV through DuckDB rather
than loading it with pandas.

**Why.** DuckDB queries CSV files directly from disk with SQL and never
materialises the file in memory. `observations.csv` alone is 382 MB at the dev
tier and roughly 10 GB at the 30k main tier — pandas would need the whole thing
resident, DuckDB streams it. The project is also SQL-primary by design, so
measurement code in SQL matches the pipeline code that follows.

**Alternative rejected.** pandas with `chunksize`. It works, but it is more code
for a worse result, and it would have meant writing the same aggregations twice
in two dialects.

### D3 — pyarrow left unpinned while everything else is pinned

**Decision.** `requirements.txt` pins exact versions for every dependency
except pyarrow.

**Why.** `pyarrow==17.0.0` produced a `ResolutionImpossible` against
`databricks-sql-connector==3.4.0`, which constrains the pyarrow range itself.
We do not care which pyarrow we get — it exists only so pandas can read and
write Parquet — so the pin was removed rather than hunting for the exact
compatible version. Resolved to 16.1.0. The reason is recorded as a comment in
the file so nobody "fixes" it later by adding a pin back.

### D4 — Entity list deliberately duplicated

**Decision.** `scripts/entities.py` holds the 12 entities, and
`pipelines/medallion/bronze/bronze.py` will hold the same list again rather
than importing it.

**Why.** `bronze.py` runs inside a Lakeflow Declarative Pipeline, where
importing from the repo root is version-dependent friction. Twelve strings are
cheaper to duplicate than to fight the import path. The docstring in
`entities.py` says so explicitly and instructs keeping them in sync — a
deliberate duplication that is documented is maintainable; an undocumented one
is a bug waiting.

---

## Task 2 — Synthea dev tier

### D5 — `generate.append_numbers_to_person_names = false`

**Decision.** Override the Synthea default so generated names are `Benjamin
Littel`, not `Abdul218`.

**Why.** This is the highest-stakes decision in phase 1 and it was nearly
missed. Phase 3's de-identification benchmark is the project's AI centerpiece,
and its headline number is name-detection F1. With trailing digits left on, the
regex `[A-Za-z]+\d+` would score near-perfectly and the entire staged
baseline-to-model comparison would measure nothing. Off, names look like real
names and the detection task is honest.

**Why it is dangerous.** It fails *silently*. Everything runs, every number is
produced, and only the meaning is destroyed. Recorded in `synthea.properties`,
`synthea/README.md`, `CLAUDE.md` and spec §4.3 for that reason.

**How it was found.** By reading an actual smoke-test note rather than trusting
the config. Worth repeating on the other generators.

### D6 — Fixed seeds and a fixed reference date

**Decision.** `-s 12345 -cs 12345 -r 20260101`, all three together.

**Why.** Without `-r`, the dataset shifts every run because Synthea generates
relative to today, which would silently invalidate every committed measurement.
All three are needed for true reproducibility: population seed, clinician seed,
and reference date.

### D7 — Smoke-test with 3 patients before any full run

**Decision.** Run 3 patients into a disposable directory before committing to a
full generation.

**Why.** A full run takes over ten minutes; three patients takes seconds. This
caught the Java 15 `UnsupportedClassVersionError` and the `Abdul218` naming
problem before either cost a full run. Recorded as a procedure in
`synthea/README.md`.

### D8 — Java 17+ required, installed as Temurin 21 LTS

**Decision.** Install Eclipse Temurin 21 rather than working around the existing
JDK 15.

**Why.** The Synthea jar is compiled to class file version 61, which requires
Java 17 or newer. There is no workaround. Temurin 21 is the current LTS.
Installed alongside JDK 15 rather than replacing it, so `java` on PATH may still
resolve to the old one — the documented command calls the Temurin binary by
absolute path.

---

## Task 3 — Calibration

### D9 — `con.read_csv(...).write_parquet(...)` instead of `COPY ... TO`

**Decision.** Use the DuckDB relation API to write the Parquet probe file.

**Why.** The original approach used
`COPY (...) TO $2 (FORMAT PARQUET)` with a bound parameter for the output path
and failed with `Parser Error: syntax error at or near "$2"`. DuckDB's `COPY ...
TO` target is a **filename literal, not an expression**, so it cannot be a bound
parameter. `$1` works in the same statement because it sits inside
`read_csv_auto(...)`, which is expression position.

**Alternative rejected.** f-stringing the path into the SQL. It works, but then
we own quote-escaping for a Windows path for no benefit. The relation API takes
the path as a Python argument, so there is nothing to escape.

### D10 — Measure Parquet bytes, not just CSV bytes

**Decision.** Write each file out as Parquet and measure the result, rather than
estimating from CSV size.

**Why.** Delta Lake stores Parquet. CSV is text — the code `44054006` costs 8
bytes on every row, where Parquet dictionary-encodes it to near nothing.
Measured: 631 MB of CSV becomes 47 MB of Parquet, a factor of 13. Sizing the
Free Edition quota from CSV would over-provision by that factor. The project's
rule is that numbers are measured, never assumed, and this is the clearest case
of why.

### D11 — `note_stats` reports total bytes and max length, not just count and mean

**Decision.** Amend the interface the spec originally specified.

**Why.** Two measured facts made count-and-mean insufficient. First, the note
corpus is **384 MB against 47 MB of Parquet for all twelve entity CSVs
combined** — a sizing document that omits the largest thing on disk is not a
sizing document. Second, mean note length is 335,034 characters but the maximum
is **3,620,548**, 10.8× higher, because Synthea writes one cumulative note per
patient so length tracks lifetime encounter count. Context-window planning needs
the max.

**Consequence recorded elsewhere.** Spec §4.3 now carries "notes must be
chunked" as a phase 3 design constraint, along with the two problems chunking
brings: spans straddling chunk boundaries, and F1 having to be scored per note
after reassembly rather than per chunk. Scoring per chunk would inflate the
headline number — the same silent-failure shape as D5.

### D12 — `SystemExit` when no input files are found

**Decision.** Both `calibrate.py` and `readmission_gate.py` exit non-zero when
their input is missing, rather than writing an empty report.

**Why.** Without the guard, a wrong `--output-dir` produces a structurally
valid report full of zeros, writes it over the committed one, and exits 0. Both
reports are decision records that later phases extrapolate from. A
plausible-looking wrong report is worse than a crash, because a crash gets
fixed.

**How it was found.** A dedicated review subagent ran the failure case rather
than reasoning about it.

---

## Task 4 — Readmission gate

### D13 — `LEAD` lookahead kept despite a known undercount

**Decision.** Find the next admission with
`LEAD(admitted) OVER (PARTITION BY patient_id ORDER BY admitted)`, accepting
that it undercounts, rather than switching to a min-after-discharge subquery or
implementing CMS transfer merging.

**Why.** 122 of 1,292 dev-tier inpatient encounters overlap a neighbouring
stay. Because `LEAD` orders by admission date, an overlapping stay can occupy
the lookahead slot and mask a genuine readmission of the stay it overlaps.

Both available shortcuts are wrong in opposite directions, and we measured the
gap rather than guessing:

| Approach | Base rate |
|---|---|
| `LEAD` (shipped) | 15.97% |
| min-after-discharge | 19.37% |
| CMS transfer merging | correct, not implemented |

min-after-discharge is not a fix — it errs in the mirror image by attributing
one readmission to two index stays. The genuinely correct answer merges
overlapping stays and transfers into a single index admission, which is real
work and belongs in phase 4's gold layer where the production label is built.

**Why shipping the cheap one is safe here.** The gate answers one question: is
this label worth building on? Both variants clear every `verdict()` threshold
and return the same PROCEED. The decision is robust to the choice, so the code
should not pay for the difference.

**Debt recorded in.** A `ponytail:` comment on `GATE_SQL`, a "Known limitation"
section in the generated report, spec §2.4 as a phase 4 obligation, and
`test_overlapping_stay_blocks_the_lookahead` so a later "fix" fails loudly.

### D14 — Two tests beyond the plan's nine

**Decision.** Add `test_verdict_covers_every_branch` and
`test_overlapping_stay_blocks_the_lookahead`.

**Why.** The Task 3 review mutation-tested the calibration suite and found 8 of
18 mutants surviving, including one that swapped the Parquet total for the CSV
total — the exact number the report tells the reader to use. The lesson
generalised: `verdict()` is pure branching that produces the project's go/no-go
and had zero coverage, which is precisely the shape that passes review untested
and then ships the wrong call. Its boundaries are pinned to PROCEED (exactly 500
admissions, exactly 1%, exactly 60%) so an off-by-one in a threshold cannot flip
a decision silently.

The overlap test exists to make D13 visible. Without it the shortcut is
invisible in the code and someone "improves" it in six months.

### D15 — Calendar-day semantics for the readmission window

**Decision.** `date_diff('day', ...)` counts calendar-day boundaries crossed,
not elapsed 24-hour periods, and this is kept deliberately.

**Why.** It matches CMS: a Tuesday 23:00 discharge followed by a Wednesday 02:00
admission is 1 day, not 0. The `> 0` test is what makes same-day re-entry a
transfer rather than a readmission. Real Synthea timestamps carry times of day
(17:04:22, not midnight), so this distinction is live rather than theoretical.
Documented as a SQL comment because the behaviour is non-obvious and looks like
a bug to anyone expecting elapsed-time arithmetic.

---

## Process

### D16 — This file, `flow.md`, and explain-then-quiz

**Decision.** From 2026-08-15, three additions to how work proceeds: log
implementation decisions here, document execution mechanics in `flow.md`, and
before any major change explain it in plain language and quiz the user 3–5
questions, implementing only once they pass.

**Why.** The project's stated purpose is hands-on learning, not shipped
software. Code that appears without being understood defeats the point, and the
existing documents capture *what was decided* without capturing *how it runs* or
*why the implementation went that way*.

**Boundary set deliberately.** Three overlapping documents converge into three
copies of the same file unless the split is explicit, so the table at the top of
this file defines it and `flow.md` repeats it.

---

## Task 5 — Databricks setup

### D17 — Databricks CLI installed via winget, not pip

**Decision.** `winget install Databricks.DatabricksCLI` (v1.14.1), replacing the
plan's original `pip install databricks-cli`.

**Why.** Two different products share the name. `pip install databricks-cli`
installs the **legacy** Python CLI, which is deprecated and has **no `bundle`
command**. The modern CLI is a standalone Go binary versioned 1.x and is not
distributed on PyPI at all. Task 7, every later deployment, and the spec's
bundles-not-clicks decision (§2.5) all require `databricks bundle deploy`, so
the pip route would have appeared to work at Task 5 and failed two tasks later
with an error that looks like a missing subcommand rather than a wrong install.

**Consequence.** The venv is irrelevant to the CLI. `databricks-sql-connector`
in the venv is a different thing again — a Python library for querying a SQL
warehouse from code, used by `run_sql.py` and later the snapshot publisher.
Three similarly-named things, one of which is a trap.

**Also worth knowing.** winget updates PATH, so the shell that ran the install
cannot see the binary; a new terminal is required. And `databricks --version`
reporting `0.x` means the legacy CLI is shadowing the new one on PATH.

### D18 — CLI auth in `~/.databrickscfg`, Python auth in `.env`

**Decision.** Let `databricks configure --token` write `~/.databrickscfg` for
the CLI, and keep `.env` for the Python scripts, rather than forcing both onto
one mechanism.

**Why.** Each tool has a native convention and both are safe: `.databrickscfg`
lives in the home directory, outside the repo entirely, and `.env` is gitignored
and verified. Unifying them would mean either exporting `.env` into the
environment in every shell before any CLI call — friction on every command,
forever — or teaching the Python scripts to parse `.databrickscfg`, which is
code written to avoid a file that already works.

**Cost accepted.** The token is stored twice, so revoking it means updating two
places. That is one extra edit on an event that happens roughly annually.

---

## Task 6 — upload

### D19 — `mkdir` runs unconditionally rather than being checked first

**Decision.** `upload.ps1` calls `databricks fs mkdir "$target"` on every run,
with no prior existence check.

**Why.** Verified idempotent — exit 0 on a second run against an existing
directory. A `fs ls`-then-branch would be two round trips to do what one
already does correctly, and the branch would itself need error handling for the
"ls failed for some other reason" case.

**What it fixes.** A freshly created Unity Catalog volume is empty, and
`fs cp` does not create intermediate directories. `landing` existed; `landing/csv`
did not. → [E13](errors.md)

### D20 — every external command call gets an exit check

**Decision.** `upload.ps1` throws on a non-zero `$LASTEXITCODE` after both the
`mkdir` and each `cp`.

**Why.** Without it the script printed twelve consecutive errors and still
finished with `Done.`. PowerShell does not stop on a native command's failure,
so the exit code is the only signal, and nothing was reading it.

**Pattern, not a one-off.** This is the third instance of the same shape — the
zeroed calibration report ([E7](errors.md)), the mutation survivors
([E8](errors.md)), and now this. A script that cannot fail is a script that
lies, and this project's outputs are decision records. Any loop calling an
external command gets an exit check.

### D21 — entity-list duplication stays trusted, not yet enforced

**Decision.** `upload.ps1` keeps its own copy of the twelve entities, matching
`scripts/entities.py`, with a comment tying them together. No test enforces the
match yet.

**Why now.** `immunizations` had silently gone missing from the upload list —
11 entities against 12 ([E15](errors.md)). Nothing failed; Task 7 would have
built an empty bronze table and the debugging would have started in Auto Loader,
two tasks downstream of the typo.

**Why not enforced yet.** `bronze.py` in Task 7 will carry the same twelve a
third time, and a test written now would need rewriting then. **The debt is
explicit: write that test as part of Task 7, covering all three lists at once.**
The duplication itself remains correct for the reason in [D4](decision.md).

---

## Task 7 — bronze pipeline

### D22 — one landing directory per entity

**Decision.** The landing volume is laid out as
`landing/csv/<entity>/<entity>.csv`, one directory per entity, and `bronze.py`
loads `csv/{entity}/` rather than a file path.

**Why.** Auto Loader watches a directory and tracks which files in it have
already been read; handed a single file it raises "is not a directory"
([E18](errors.md)). That forces a choice, and the flat alternative loses on
merit rather than on ceremony:

| Option | Cost |
|---|---|
| Directory per entity *(chosen)* | Restructure once, one line in two files |
| Flat `csv/` + `pathGlobFilter` | Free today; all twelve streams list all twelve files per poll, forever |

The decider is the second batch. With a directory per entity, ingesting a new
Synthea run means dropping `patients_2027.csv` into `csv/patients/` — no code
change, which is the entire reason for using Auto Loader over a plain read. The
flat layout makes every future batch land in a directory that twelve streams are
all scanning and filtering.

**Migration cost was near zero.** `databricks fs cp` copies between volume
paths server-side, so the 631 MB was reorganised without re-uploading.

**Left behind deliberately.** The original flat `csv/*.csv` files still exist,
duplicating 631 MB. Nothing watches `csv/` itself so they are inert; deleting
them is pending an explicit go-ahead.

### D23 — the three-way entity list is now enforced, not trusted

**Decision.** `tests/test_entity_lists_match.py` parses the entity list out of
`upload.ps1` and `bronze.py` and asserts both equal `scripts.entities.ENTITIES`.

**Why now.** [D21](decision.md) deferred this until the third copy existed.
`bronze.py` created it. The duplication is still correct for the reasons in
[D4](decision.md) — a Lakeflow pipeline cannot cleanly import from the repo root
and PowerShell cannot import Python at all — but "keep these in sync" as a
comment had already failed once ([E15](errors.md)), silently.

**Verified by mutation.** Deleting `immunizations` from either file makes the
suite fail. A sync test that does not actually catch a missing entity is worse
than none, because it converts a real risk into a false sense of coverage.

**Bounded on purpose.** It compares list *contents and order*, nothing else. It
is not a parser for either language, and it should never grow into one.

---

## Task 8 — snapshot publish

### D24 — `python-dotenv` and a single `scripts/dbx.py`

**Decision.** Add `python-dotenv==1.0.1`, and route every warehouse connection
through `dbx.connect()`.

**Why a dependency at all.** The alternative is four lines splitting `.env` on
the first `=`. It handles today's file and quietly mis-parses a quoted value, an
`export ` prefix, or a value containing `=` — edge cases that surface while
debugging something else entirely. 19 kB of pure Python is a fair price for not
owning a parser.

**Why a shared module rather than `load_dotenv()` in each script.** The bug was
in two scripts, not one ([E21](errors.md)): `run_sql.py` had it too and appeared
to work only because a shell had exported the variables. Fixing the reported
caller would have left the other broken-by-luck. Both also carried the same
`sql.connect(...)` block, so one function removes the duplication and the class
of bug at once.

**`override=False` is deliberate.** A variable already exported in the shell
beats `.env`, which is what lets CI inject secrets with no file on disk.

**Failure message widened.** The original raised on whichever variable it read
first, naming `DATABRICKS_HOST` even when all three were missing. `connect()`
lists everything absent and points at `.env.example`.

---

## Phase 2a

### D28 — silver publishes from the same pipeline, addressed by full name

**Decision.** Silver tables are written by the existing `medallion` pipeline
using fully-qualified names — `@dlt.table(name=f"{CATALOG}.silver.<table>")` —
with the catalog supplied as a pipeline configuration value, not hardcoded.

**Why it had to be tested rather than assumed.** The pipeline's default schema
is `bronze`, fixed in `databricks.yml`. Databricks documents that one pipeline
can publish to several schemas via fully-qualified names, but only in the newer
default publishing mode, and the migration doc describes how to identify
*legacy* pipelines without giving the inverse test. The deployed spec has
`schema` and no `target`, which suggests the newer mode — suggests, not proves.

**How it was settled.** A two-table throwaway spike: one table depending on
nothing (does writing elsewhere work) and one reading `bronze.br_patients` (does
reading across schemas work). Two tables rather than one so a failure would
localise. Both succeeded — `ok` and `1148` — and both were dropped afterwards.

**Why the catalog is configuration.** Databricks' own guidance: code that
references a second schema should take it as a pipeline parameter rather than
hardcoding it, so dev and prod differ by configuration alone. `landing_path` and
`batch_id` already worked this way.

**What this avoided.** The fallback, had it failed, was recreating the pipeline
in the newer mode — discarding Auto Loader's file-tracking state and forcing a
re-ingest of 631 MB. Finding that out after writing ten silver tables would have
been the expensive version.

### D29 — the phase 2 spec's vocabulary model was wrong, and silver follows the data

**Decision.** `dim_code` is built from the measured contents of the files, not
from the spec's four-source table. Recorded in `silver-model-findings.md`.

**What the measurement changed.** Four things the spec assumed are false:
`allergies` holds SNOMED *and* RxNorm in one file; SNOMED is written as both
`http://snomed.info/sct` and `SNOMED-CT`; `procedures` contributes 380 SNOMED
codes that overlap `conditions` by zero; and codes with two different
descriptions already exist.

**Why this went in a published document rather than the plan.** The plan is
local. These are measurements of the dataset — the same category as
`calibration.md` — and every later decision is checked against them.

**The rule it establishes.** Specs describe intent; files describe fact. Where
they disagree, the file wins and the spec gets corrected. Six of this project's
errors came from reference code written before anything was run.

### D30 — `code_key` is a hash, not a counter

**Decision.** `xxhash64(system, code)`.

**Why not a counter.** Bronze exists so silver can be dropped and rebuilt
without re-uploading 631 MB. A counter breaks that: rebuild, and every id is
reassigned, so every fact row now points at a different code while still
looking perfectly valid. **The failure is silent and total.** A hash of the
natural key returns the same id every time, from any machine, in any order.

**Why `xxhash64` rather than `sha2`.** A 64-bit integer instead of a 64-character
hex string, for a column that appears in every fact table. Collision risk across
1,246 codes is around 1 in 10^13. Verified after the build: 1,246 rows, 1,246
distinct keys.

**Why a surrogate key at all**, when `(system, code)` is already unique: one
join column instead of two in seven fact tables. Thin, but real.

### D31 — latest description wins

**Decision.** Where a code carries more than one description, take the one with
the most recent timestamp; ties break alphabetically so the result is
deterministic.

**Why a rule was needed at all.** Not defensive — `6299-2`, `8310-5`, `312961`,
`133` and others already carry two descriptions each. Without a rule the join
produces duplicate keys and the build fails.

**Why latest.** Descriptions get revised, not randomised; the newest is the
current one. The alphabetical tiebreak matters because two rows sharing a
timestamp would otherwise make the build non-deterministic — it would pass, and
produce a different answer next time.

### D32 — four canonical encounter classes, and a separate readmission role

**Two deviations from spec §3.4. Both flagged for review.**

**Decision.** `encounter_class_map` maps Synthea's ten encounter classes to
`acute / post_acute / ambulatory / preventive`, plus a second column
`readmission_role`.

**Why a fourth class.** The spec names three and lists five encounter classes.
The data has ten. `snf` and `hospice` are facility stays — calling them
ambulatory is plainly wrong, and they are not acute care either. The spec never
considered them because nobody had looked at the data.

**Why a second column.** One column cannot answer both "what kind of care was
this" and "does this count toward readmission". Conflating them is precisely how
a transfer to skilled nursing silently becomes a readmission.

**The clinical calls, which are the flagged part.** `snf` is
`transfer_target` — patients are discharged *to* skilled nursing, so arriving
there is not a readmission. `hospice` is `excluded` — CMS methodology generally
removes hospice from the measure rather than classifying it. These change the
phase 4 number. 625 snf and 191 hospice encounters are affected.

**Enforced, not trusted.** `unmapped_encounter_class` returns every bronze
class with no mapping. It must stay empty; it is 0 today. An unmapped class
would otherwise become NULL and drop encounters out of every denominator.

## Phase 2b — orchestration and reproducibility

### D33 — `DatabricksSubmitRunOperator` with a `pipeline_task`, not `RunNow`

**Deviation from spec §3.7**, which names `DatabricksRunNowOperator`.

**Why not RunNow.** It takes `job_id` or `job_name` and nothing else. It runs
**Jobs**; the medallion is a **Pipeline**, a different object. Using it would
mean creating a Job resource purely to wrap the pipeline.

**Why SubmitRun.** It sends a one-time run to `runs/submit` with a
`pipeline_task`, then polls it to a terminal state. Trigger and wait are one
task, and nothing new has to exist in the workspace.

**Proven before Airflow existed.** `databricks jobs submit` calls the same
endpoint. Run on 18 Sep: `TERMINATED SUCCESS` after ~5 minutes; the pipeline's
update history showed a new `COMPLETED` update with cause `JOB_TASK`; and
`list-pipelines` still showed exactly one pipeline — a submitted run starts
the existing pipeline, it does not create a second one against Free Edition's
one-pipeline limit. The first attempt, the day before, was refused for reasons
unrelated to the request ([E25](errors.md#e25)).

**Proven to fail properly, through Airflow**, with 2a's second real bug put back
(`SELECT * EXCEPT (violations)`):

| Run | Airflow task | Databricks |
|---|---|---|
| Good SQL | green, ~5 min | `COMPLETED`, cause `JOB_TASK` |
| Broken SQL | **red**, ~14 min | `FAILED` once + 5 × `RETRY_ON_FAILURE`, then stopped; `UNRESOLVED_COLUMN … violations` |
| Reverted | green | `COMPLETED` |

The task log shows the operator polling `RUNNING` and ending on the terminal
state, so green means the pipeline *finished*, not that it was *submitted*.
`retries=0` held: one burst of the pipeline's own retries, no second round from
Airflow.

**One gap.** The Airflow log says only "refer to the logs for this pipeline in
the pipelines page" — the actual `UNRESOLVED_COLUMN` lives in Databricks'
pipeline events, one hop away. Red is reliable; the reason is not in Airflow.

### D34 — no sqlfluff; `--validate-only` is the SQL check

**Deviation from spec §3.9.**

**Why not sqlfluff.** Tested with 4.3.0, `databricks` dialect: it cannot parse
`CONSTRAINT … EXPECT … ON VIOLATION DROP ROW`, which nine tables use. Default
config fails those nine forever; `ignore = parsing` makes them pass and also
passes `SELECT a,, b` with exit 0. Neither configuration can catch broken SQL
here, and both SQL bugs this project has actually hit were parse errors.

**Why `--validate-only`.** Databricks compiles the pipeline's real source against
the real catalog without materialising anything. Proven on 18 Sep with 2a's
actual bug put back in (`CONSTRAINT` after `TBLPROPERTIES`):

| Run | Result |
|---|---|
| Current SQL | `COMPLETED`, ~90 s |
| `CONSTRAINT` moved after `TBLPROPERTIES` | `FAILED` — `PARSE_SYNTAX_ERROR … at or near 'CONSTRAINT'` |
| Reverted | `COMPLETED` |

**Why local, not CI.** It needs Databricks compute; running it on every pull
request spends the quota whose exhaustion locks the workspace. It is written
into the README as the step before pushing pipeline SQL.

**What would reverse this.** sqlfluff's dialect learning `CONSTRAINT … EXPECT`.

### D35 — Synthea built from commit `7e08387`; reproduces to 0.004%

**Decision.** `synthea/Dockerfile` builds Synthea from commit
`7e08387c68a7f0e21d13076609a159fd473fc902` and bakes in the recorded seeds,
reference date, end date and properties file.

**Why a commit, not a release.** The recorded dataset came from Synthea's rolling
`master-branch-latest` build, overwritten on 18 Aug. The newest stable release,
v4.0.0, is different code and means re-baselining every phase 1 measurement. A
commit hash cannot be overwritten.

**What was verified.** The rebuilt jar matches the original on commit
(`Build-Version: 7e08387`, after [E29](errors.md#e29)), JDK (17.0.20) and size
to within 18 bytes. The runtime is the same Java 21.0.12 as the recorded run.

**What was not achieved: an identical dataset.** Three generation runs:

| Run | Patients | Identical patient rows | Cause of difference |
|---|---|---|---|
| Default heap | 1,138 | — | JVM out of memory ([E30](errors.md#e30)) |
| `-Xmx3g` | 1,147 | — | simulated to run date ([E31](errors.md#e31)) |
| `-Xmx3g -e 20260808` | 1,147 | **861 of 1,148** | **not identified** |

The last run matches the recorded one on patient `Id` for 1,143 people and on
the longest clinical note to the character, but about a quarter of patients
differ and the totals are ~0.2% off (3,269,605 rows against 3,277,048).

**Stopped at the time-box, deliberately.** The plan set two hours for this
task, and each diagnostic run costs 35 minutes. Candidate causes, none tested:
thread scheduling in Synthea's multi-threaded generator; provider assignment
depending on shared state across threads; the recorded run's end being
22:18 UTC on 8 Aug where `-e` ends at midnight.

**What this means in practice.** The container regenerates a dataset **of the
same shape and scale** — same code, same config, same population seeds — but
not the byte-identical one `calibration.md` measured. The committed
measurements remain true of the dataset actually in the lakehouse. What cannot
be claimed is "rerun this and get the same numbers".

**Threading ruled out (19 Sep).** A fourth run with
`--generate.thread_pool_size=1` produced 1,147 patients, 861 identical to the
recorded run, and **the same row count in every table and the same CSV bytes**
as the multi-threaded container run. The container is deterministic; it is
consistently different from the laptop run. The end-time theory is out too:
the container stops earlier in the day on 8 Aug yet has *more* encounters
(188,511 against 187,540).

**Timezone was the main cause — confirmed 19 Sep.** The recorded run was made on
a laptop in US Central time; the container runs UTC, and Synthea converts
timestamps to dates in the JVM's zone. A fifth run with
`-Duser.timezone=America/Chicago`:

| | UTC (run 3) | Chicago (run 5) | Recorded |
|---|---|---|---|
| Records | 1,147 / 1,000 / 147 | **1,148 / 1,000 / 148** | 1,148 / 1,000 / 148 |
| Identical patient rows | 861 | **1,136** | — |
| Total rows | 3,269,605 | **3,277,180** | 3,277,048 |
| Encounters not reproduced | — | **15 of 187,540** | — |

The 12 non-identical patients are the same people — same name, birth date,
address — differing only in the running `HEALTHCARE_EXPENSES/COVERAGE` totals.

**What remains, and why it stays.**

1. **End time of day.** Every leftover encounter falls between 7 Jul and 8 Aug
   2026; 7 are on 8 Aug itself, which the container has none of. The recorded
   run simulated up to 22:18 on 8 Aug; `-e` accepts only a date and stops at
   its start. Synthea offers no finer control, so this residue is permanent.
2. **Line endings.** The recorded CSVs were written on Windows with `\r\n`; the
   container writes `\n`. Every file is exactly one byte per line smaller —
   same data, different bytes. This is why `calibration.md`'s byte columns can
   never match from Linux. (Git Bash's `grep` strips `\r` and reported zero —
   count raw bytes when checking this.)

The timezone is now baked into the image's entrypoint.

**Verdict.** The image reproduces the recorded dataset to within the final
weeks before the cutoff: identical patient roster, identical counts for seven of
twelve tables, 132 rows different out of 3.28 million (0.004%). Not
byte-identical, and it cannot be from Linux.

**Resolved by option (a).** Three options were on the table after the time-box:
(a) keep testing causes, (b) accept "same shape", (c) re-baseline phase 1 on
container output. (a) was chosen: the single-threaded run ruled threading out,
the timezone run found the cause. No re-baseline is needed; `calibration.md`
stands.

### D36 — the snapshot stays a manual step after the DAG

**Deviation from spec §3.7**, which had the DAG publish the snapshot.

The snapshot's output is a committed file; it only reaches the live app after a
commit and push, which a DAG cannot and should not do. Automating it would turn
two human steps into one while adding container plumbing, three credentials and
a new failure mode — a half-automation that looks finished and is not.

**What would change this.** Anything consuming the snapshot without a human in
between.

### D37 — Airflow reads the repo's one `.env`; no second credential file

**Deviation from the 2b plan**, which had the token copied into
`orchestration/.env`.

**Decision.** `docker compose --env-file ../.env` makes the root `.env`'s
`DATABRICKS_HOST` and `DATABRICKS_TOKEN` available to the compose file, which
builds `AIRFLOW_CONN_DATABRICKS_DEFAULT` from them as a JSON connection.

**Why.** Two files holding the same token means two places to rotate it and
two places for it to leak. With one, the token is never typed into a second
file, a DAG, or Airflow's UI. `orchestration/.env` stays gitignored anyway, in
case anyone creates one.

**Cost.** Every compose command needs `--env-file ../.env`. Forgetting it gives
a connection with an empty host and token, which fails loudly at the first
Databricks call rather than silently.

### D38 — Airflow on LocalExecutor, five containers not eight

**Deviation from the stock compose file**, which runs CeleryExecutor with Redis,
a Celery worker and a triggerer.

**Why.** Celery exists to spread tasks across machines; there is one laptop.
Docker Desktop here gets ~4 GB of an 8 GB machine, and the one time two builds
shared it the engine froze ([E27](errors.md#e27)). LocalExecutor runs tasks as
scheduler subprocesses: no broker, no worker. The triggerer only serves
deferrable operators, and `DatabricksSubmitRunOperator` runs non-deferrable by
default.

**Measured.** postgres, api-server, scheduler and DAG processor together use
~1.15 GB at idle.

**What would reverse it.** Deferrable operators (bring back the triggerer), or
more than one machine running tasks (bring back Celery).

### D39 — the PR gate's status is unknown, and that is recorded rather than assumed

**Finding, not a decision.** Phase 2b's Task 0 was to see `.github/workflows/pr.yml`
go green on a clean branch and red on a broken one, and to write down both dates.
There are no dates. The workflow has never executed: the GitHub API reports
`"total_count": 0` for workflow runs and no pull request has ever been opened
on this repository. Every commit went straight to `main`, and the trigger is
`on: pull_request`. [E33](errors.md#e33).

**Why this is worth a decision entry.** The file was added specifically because
[E16](errors.md#e16) and [E22](errors.md#e22) put broken code on `main` twice.
It has not prevented a third occurrence; it has not had the chance to. Leaving
the README implying an enforced gate would be the fourth instance of the same
failure shape this log already names.

**Deferred to phase 3a**, where the choice is between opening one throwaway PR
to prove the mechanism and adding a `push` trigger to match how this repository
is actually worked. They solve different problems and the trade-off is written
out in E33.

### D40 — phase 3 splits into 3a and 3b

**Decision.** The spec's phase 3 ships as two phases. 3a is structural
governance — Unity Catalog tags, column masks, row filters, clearance table,
audit view. 3b is the de-identification AI — note chunking, the three detection
stages, MLflow evaluation, k-anonymity.

**Why.** They share the word PHI and nothing else. 3a is SQL against the
catalog and costs almost no compute; 3b is quota-bound model work on 1,148
notes averaging 335 KB. Held together, the finished governance layer waits on
NER debugging before anything is demonstrable.

**The consequence that shaped 3a.** `silver.patient` is a materialized view
owned by the Lakeflow pipeline, so `ALTER TABLE … SET MASK` applied from
outside is **not in the pipeline source and is lost on the next full refresh** —
silently, with no error. Masks and row filters are therefore declared inside
`pipelines/medallion/silver/patient.sql`, making the pipeline source the one
record of what is protected. The mask functions and the clearance table cannot
live there, because a pipeline cannot `CREATE FUNCTION` and its outputs are
read-only, so they bootstrap separately and the pipeline fails loudly if that
bootstrap has not run.

### D41 — the governance probe: all five mechanisms work on Free Edition

Three things in D40 were assumed. `sql/probe_governance.sql` tested them before
any of 3a was built. **All five passed**, and two of them were expected to fail.

| Probe | Result |
|---|---|
| P1 — create a masking function | Works |
| P2 — a masking function that reads a table | **Works.** Predicted to be the coin-flip |
| P3 — attach the mask, and see it flip | Works. `Lucius Emard` with a clearance row, `***` after deleting it |
| P4 — column tags | Works. `information_schema.column_tags` returns the tag |
| P5 — `system.access.audit` | **Exists and is populated.** Predicted to be absent |

P2 passing is what matters most: the spec's clearance-table design survives, so
the mask can be demonstrated opening and closing on a one-account workspace
without depending on UC groups. P5 passing means the audit view stays in scope
rather than becoming a degradation-table row.

**Two questions the probe did not answer, and must not be assumed from it:**

- **P4 ran against a plain Delta table, not a pipeline-owned materialized
  view.** Whether a column tag survives a full refresh of `silver.patient` is
  still unknown, and it is the whole reason tags cannot live in the pipeline
  source. Test it by full-refreshing and re-querying `column_tags`.
- **The single P5 row is a system event** — `workspace_id: 0`,
  `user_identity.email: System-User`, `service_name: unityCatalog`. It proves
  the table exists and fills; it does not prove a human `SELECT` against a
  PHI-tagged column is captured with an attributable identity. `system.query`
  also exists and may be the better source for the audit view.

Predicting two of five wrongly is the argument for having run the probe at all:
3a would otherwise have been planned around a clearance design believed fragile
and an audit view believed impossible.

### D42 — ABAC exists here, and it may remove D40's central constraint

`sql/probe_tag_mask_link.sql` answered three more questions.

**P7 — an applied mask is visible as metadata.**
`information_schema.column_masks` returns
`probe_link / ssn / healthcare_dev.ops.probe_hide`.

**P8 — the tag-versus-mask drift check works, and was tested in both
directions.** The probe tags two columns `phi_category` and masks only one. The
check returns `city` and not `ssn` — so it catches an unmasked PHI column, and
does not cry wolf on a masked one. A check only ever seen passing is [E33](errors.md#e33)
again; this one has been seen failing on purpose.

**P9 — `information_schema.abac_policy_definitions` exists.** Its columns say
what a policy is: `policy_type` takes `COLUMN_MASK` and `ROW_FILTER`,
`on_securable_type` takes `CATALOG`, `SCHEMA` or `TABLE`, and there are
`match_columns` and `when_condition`.

**Why that matters more than it looks.** D40's central problem is that a mask
attached to `silver.patient` is lost when the pipeline recreates the view, which
is why masks were to be written into the pipeline source. A policy attached to
the **schema**, matching columns by condition, is not attached to the view at
all — so a full refresh cannot drop it. If that works, masks come out of
`patient.sql` entirely and one policy per Safe Harbor category replaces a MASK
clause on every column.

**It also inverts which artefact is load-bearing.** Under ABAC the tag stops
being a label and becomes the thing the policy matches on. A tag lost in a full
refresh would then silently unmask the column — a worse failure than today's,
and the reason P8's drift check moves from nice-to-have to required.

**Still unproven, and not to be assumed from a table's column list:** that
`CREATE POLICY` is permitted on Free Edition, and that it can match columns by
tag rather than by name. The next probe creates one. D40 stands until it does.

### D43 — masks are ABAC policies on the schema, not MASK clauses on columns

**This replaces D40's approach.** `sql/probe_abac.sql` created a working
tag-driven column mask on Free Edition.

**The first attempt failed**, and the error is the useful part:

```
UC_INVALID_POLICY_CONDITION … Unknown tag policy key `phi_category`
```

**ABAC matches governed tags, not the free-form kind.** A governed tag is an
account-level key with a declared value list, registered with
`CREATE GOVERNED TAG phi_category VALUES ('name','ssn','date','geography','contact')`.
`ALTER … SET TAGS` will happily write any key it is handed; only a registered
one can be matched by a policy. Two kinds of tag, one word — [errors.md](errors.md)
Pattern 4 again.

**What works, measured:**

| Probe | Result |
|---|---|
| P10 `CREATE GOVERNED TAG` | Permitted on this account |
| P11 policy matching the tag **key**, `has_tag('phi_category')` | Registered as `COLUMN_MASK` on `SCHEMA`; both tagged columns returned `***` |
| P12 policy matching the tag **value**, `has_tag_value('phi_category','ssn')` | `ssn` → `***`, `city` → `Boston` |

P12 is the one that decides the shape of the work: **one policy per Safe Harbor
category**, each pointing at the mask function for that category, rather than a
`MASK` clause on each of twenty columns.

**Why this outranks D40's design.** The policy is attached to the *schema*. It
is not part of `silver.patient`, so the pipeline cannot drop it when it
recreates the view — which was D40's entire reason for pushing masks into the
pipeline source. `pipelines/medallion/silver/patient.sql` stays untouched by
governance, and the Databricks docs state column mask policies apply to
materialized views and streaming tables.

**The risk moves rather than disappearing.** The tag is now the load-bearing
part: lose it and the policy stops matching and the column silently unmasks.
Under D40 a lost `MASK` clause would at least show in a diff of the pipeline
source. So the P8 drift check is not optional, and it should compare against
governed-tag assignments.

**Tested as far as it can be cheaply.** Tags survive `CREATE OR REPLACE TABLE`
and the mask still applies afterwards. **That is a proxy, not the real thing** —
a Lakeflow full refresh of a materialized view is not a `CREATE OR REPLACE
TABLE`, and the difference is exactly where a silent unmasking would hide. The
authoritative test is a full refresh of one small table with
`--full-refresh-selection`, and it costs a serverless wake-up against the daily
quota, so it is a deliberate step rather than something to slip into a probe.

**D42's drift check was superseded before it was ever used.** It joined
`column_tags` to `information_schema.column_masks`, which is correct only for
`ALTER COLUMN … SET MASK`. Under D43's ABAC design `column_masks` stays empty,
so that check would report all 19 protected columns as unprotected, for ever.
It was verified in both directions — against a design abandoned one decision
later, and the verification was not repeated. [E37](errors.md#e37).

### D44 — phase 3a as built

| | |
|---|---|
| Governed tag | `phi_category`, 8 values |
| Mask functions | `mask_text`, `mask_zip`, `mask_date`, `mask_point`, all gated by `is_cleared()` |
| Tagged columns | 19 on `silver.patient`, 19 on `ops.quarantine_patient` |
| Column mask policies | 4 per schema, 8 total |
| Row filter policy | 1, on `silver` |
| Audit view | `ops.phi_access_audit` |

**Four mask policies, not eight.** `MATCH COLUMNS` accepts a disjunction, so
the five tag values sharing `mask_text` — `name`, `geography`, `ssn`,
`license`, `other_id` — collapse into one policy. `zip`, `date` and `geo_point`
need their own because each names a different mask function.

**The vocabulary splits on type as well as category.** A mask returns the
column's own type, so `latitude`/`longitude` (DOUBLE) cannot share the STRING
mask the other geography columns use — hence `geo_point`. And `ZIP` truncates
where `ADDRESS` redacts, so it cannot share `geography` either. Both splits are
mechanical consequences of the platform, not of HIPAA.

**Two columns are deliberately untagged.** `STATE`, because Safe Harbor permits
state and the row filter keys off it. `patient_id`, because masking a join key
breaks every downstream join — Safe Harbor does cover it, and a surrogate key
in the `deid` branch is 3b's answer.

**Verified, not assumed:**

- Masks flip both ways on the real table — `999-27-2324` → `***`,
  `01730` → `017`, `2022-11-30` → `2022-01-01`, coordinates → `NULL`
- **Tags survive a Lakeflow full refresh.** `--full-refresh-selection
  silver.patient` completed, the census still read 19/19, masking still worked.
  That was the design's last open risk
- The drift check was proven failing, by dropping `mask_phi_zip` and watching
  `zip` appear, then restored

### D45 — the row filter demonstrates a mechanism, not a policy

`filter_patient_state` restricts rows by `STATE` against `ops.phi_clearance`.
Verified: scope `*` → 1,148 rows, scope `Rhode Island` → 0, scope
`Massachusetts` → 1,148.

**Every patient in this dataset is in Massachusetts**, so this filter can only
ever be all-or-nothing. It is included because it proves the mechanism and
because a second state would make it real with no code change — not because it
is doing segregation work. Said plainly here rather than left to imply more.

It uses a second governed tag, `row_scope`, rather than `phi_category`. STATE
is not an identifier under Safe Harbor, and tagging it `phi_category` would
have masked it and put it under the wrong policy. The tag says what a column is
*for*, not what kind of identifier it is.

### D46 — the audit view reads query history, not the access log

`ops.phi_access_audit` is built on `system.query.history`. Both it and
`system.access.audit` exist here, and access.audit has 19,462 user-attributed
rows — but they record catalog operations like `getTableById`, which answers
"was this object resolved", not "did a person read this data". query.history
carries the statement text and who ran it.

Its PHI table list is derived from `column_tags` rather than hardcoded, so
tagging a new table adds it to the audit with no second place to update.

**It matches on statement text, which is an upper bound and not a census.** A
read through another view is missed, and `patient` is a substring of
`quarantine_patient` so one read matches both. The precise alternative is
`access.audit.request_params`, which is far less legible. Stated here so no
number from this view is ever quoted as exact.

### D47 — the clearance table is the ceiling, and it is not access control

Nothing prevents `INSERT INTO ops.phi_clearance VALUES (current_user(), 'full')`.
Any reader who can query the masked data can clear themselves.

On a one-account workspace there is nobody to defend against, and UC groups are
the production answer the spec already names. But **"this project implements
column masks" implies more than is delivered**, so the gap is recorded rather
than left for a reader to discover. The production fix is `REVOKE MODIFY` on
`ops.phi_clearance` from everyone except an admin group.

**Two hazards that fail silently, both from `TO account users` covering the
identity the pipeline runs as:**

- Gold is built from *identified* silver on purpose, because readmission
  windows need true dates. Build gold with no clearance row and every gold
  table fills with `***` and `2022-01-01`, with no error anywhere.
- Worse, the row filter: build gold with the wrong `scope_state` and gold comes
  out **empty**, also with no error.

`sql/governance_check.sql` catches neither. It compares tags to policies, not
clearance to intent. Check `ops.phi_clearance` before any gold build.

## Task 9 — the public app

### D25 — the app gets its own `requirements.txt`

**Decision.** `app/requirements.txt` pins exactly what the Streamlit app
imports — `streamlit`, `pandas`, `pyarrow` — and the root `requirements.txt`
keeps the full project set unchanged.

**Why not one file.** They serve two different machines. Locally, one
environment running the tests, the linter, DuckDB calibration and the warehouse
scripts is correct — splitting it would mean managing two venvs to save
nothing. On Streamlit Cloud only three packages are ever imported, and the
extras are not merely unused: `databricks-sql-connector` caps pyarrow below the
version with wheels for the deploy interpreter, which is precisely what broke
the deploy ([E23](errors.md)). The unused dependency was the failing one.

**Why this location rather than a `requirements-app.txt` at the root.**
Streamlit Cloud searches the entrypoint's directory *before* the repo root and
uses the first dependency file it finds. Putting it next to `streamlit_app.py`
means Cloud picks it with no configuration, and it sits where a reader looking
at the app will see it. A root-level second file would need Cloud to be told
about it and would leave two similarly named files competing at the root.

**Why pinned, and pinned to these versions.** They match the local `.venv`
exactly, so what is deployed is what was tested. The root file's reasoning for
leaving pyarrow unpinned ([D3](decision.md)) was the connector's range
constraint — with the connector gone from this file, the constraint is gone and
there is no reason not to pin.

**Why `pyarrow` is listed at all** when `streamlit` already depends on it:
`pd.read_parquet` is our code path's requirement, not a transitive accident.
An explicit line survives a future release dropping the transitive edge.

**Known ceiling.** Two files now list overlapping packages, and nothing checks
that the three shared pins agree. If they drift, the app is tested against one
pandas and deployed against another. Not enforced today — the CI in phase 2 is
where a check belongs, alongside the lint gate ([E22](errors.md)).

**Correction.** Pinning to the local versions was right, but it is only
*coherent* once the deploy interpreter matches the local one — see D26. Pinned
versions and a different Python are worse than loose versions, because the pin
guarantees the resolver cannot route around a missing wheel.

### D26 — the deployed app runs Python 3.12, chosen explicitly

**Decision.** Streamlit Cloud's Python version is set to **3.12**, matching the
local `.venv`, rather than left on the platform default.

**Why not the default.** The default moved to 3.14, which at the time had no
wheels for pyarrow 16, pandas 2.2.3 or duckdb 1.1.3. Every install became a
source build and the deploy failed ([E23](errors.md)). Streamlit's own guidance
is to develop on the version you deploy; taking the default means the public app
runs on an interpreter that is never once exercised locally.

**Why 3.12 and not the newest with wheels.** 3.12 is what the project's venv,
`ruff`'s `target-version` and every tested run already use. Matching them costs
nothing. Chasing the newest interpreter would buy nothing this app can use and
reintroduce the same wheel-availability gamble on the next Python release.

**Where it lives.** In the Streamlit Cloud app settings, not in the repository —
the platform provides no file-based way to pin it. **This is the one piece of
deployment configuration with no representation in git.** If the app is ever
recreated, the version must be set again by hand, and a deploy that fails on
source builds is the symptom that it was not.

---

## Process

### D27 — the plan, the spec and `CLAUDE.md` are local, and purged from history

**Decision.** `CLAUDE.md`, `docs/plans/` and `docs/specs/` are gitignored and
were removed from every commit with `git filter-branch --index-filter`. The rest
of `docs/` stays published.

**Why these three and not the rest.** They are working instruments. The plan is
a task list with reference code that is already superseded by what actually
shipped; the spec is an authority for the author, not an explanation for a
reader; `CLAUDE.md` is addressed to a tool. The published files answer a
reader's questions instead: what the data measures (`calibration.md`), whether
the ML target is viable (`readmission-gate.md`), why the implementation went
this way (`decision.md`), how it runs (`flow.md`), what broke (`errors.md`).

**Why the rest of `docs/` was argued for.** Removing it was considered and
rejected. The documentation is the part of this repository that is not
reproducible from a tutorial, and the README cites it as evidence.

**What the purge cost.** Three commits existed only to add these files and were
dropped by `--prune-empty`, so the history no longer records that a plan was
written before the code. Twenty commits remain of twenty-three. The tree at
`HEAD` is byte-identical before and after — only history changed.

**What it does not achieve.** GitHub keeps unreferenced objects reachable by
SHA until it garbage-collects, so someone holding an old commit id may still
fetch the old content for a while. A history purge reduces exposure; it is not
a revocation. **Nothing sensitive was in these files** — that was verified
before removal, and it is the only reason this was a tidiness decision rather
than an incident.

### D48 — phase 3b's probes: the platform is there, the offsets are not

`sql/probe_3b.sql`, run before any of 3b was planned in detail.

| Probe | Result |
|---|---|
| P1 `ai_query` on a Foundation Model endpoint | **Works.** `databricks-meta-llama-3-3-70b-instruct` returned `OK` |
| P2 `system.serving` | Exists. `served_entities` is empty — it tracks customer-created endpoints, not the pay-per-token foundation models |
| P3 `system.mlflow` | `experiments_latest`, `runs_latest`, `run_metrics_history` all present |
| P4 auto-applied `class.*` tags | **Zero.** Nothing classifies columns automatically here |

**P1 passing means stage 3 exists.** The spec assumed in-platform APIs because
outbound internet is restricted; they are genuinely available.

P4 confirms 3a's decision to hand-tag nineteen columns was not wasted work —
there was no scanner to lean on.

**The finding that shapes stage 3.** Asked to return PHI as JSON with character
offsets, on a real 700-character note chunk, the model got every *category*
right and most *offsets* wrong:

| Returned | Claimed offset | Actual | |
|---|---:|---:|---|
| `2017-10-13` | 5 | 1 | off by +4 |
| `Aaron` | 76 | 76 | correct |
| `62` | 94 | 87 | off by +7 |

One in three. `chunk[5:15]` is `'-10-13\n\n# '` — a span that would redact the
wrong characters and leave part of the date in place.

**So stage 3 must never trust the model's offsets.** It takes the returned
*text*, which was correct in all three cases, and resolves it back to an offset
by searching the chunk. That brings its own problem to solve rather than
discover later: when the returned text occurs more than once in a chunk, which
occurrence was meant. Counting how often that ambiguity arises is part of
stage 3's result, not a footnote to it.

**P5 is not answered.** Whether `transformers` installs on serverless and a
clinical NER model runs on CPU in usable time cannot be tested from SQL. It
needs a notebook, and it decides whether stage 2 runs on all 1,148 notes or
only the held-out sample.

### D49 — correction to D47: the clearance table cannot be secured here at all

D47 said the clearance table "has no ACL" and that "any reader who can query
the masked data can clear themselves", with `REVOKE MODIFY` named as the fix.
Both halves are wrong, and checking rather than asserting is what showed it.

```
SHOW GRANTS ON TABLE healthcare_dev.ops.phi_clearance   -- no rows
SHOW GRANTS ON SCHEMA healthcare_dev.ops                -- no rows
Owner: tanaygattani8@gmail.com
```

**There are no grants because there is nobody to grant to.** This workspace has
exactly one principal, and that principal owns every object in it. No other
reader exists who could clear themselves, so the hole D47 describes has no
population to exploit it — and `REVOKE MODIFY` would be a no-op, because
nothing is granted and an owner cannot be revoked from their own table.

**The accurate statement is stronger and less flattering.** Separation of
duties is not weakly implemented here; it is **impossible** here. The clearance
table demonstrates a mechanism working in both directions, which is worth
having. It enforces nothing against the only account that exists.

**The production fix is not a REVOKE.** It is a second principal: a service
principal or group that owns `ops`, with the analyst identity granted `SELECT`
on `silver` and nothing on `ops`. That cannot be built on Free Edition, so it
is recorded rather than implemented, and the README's degradation table carries
it.

**Why this correction matters more than the original entry.** D47 described a
lock with a weak key. The truth is that the door frame has no wall around it.
Those read very differently to anyone judging whether this project's governance
is real, and the second one is what is actually true.

### D50 — what is actually in the notes, and it is not what the spec assumed

Step 3 was run on ten patients before landing anything, and reading the output
changed the phase. Spec §4.3 says the notes contain "the generated patient's
real name, address, dates and identifiers". Measured, on one 122,204-character
note:

| Detail | Times it appears |
|---|---:|
| First name (`Lucius`) | 89 |
| Dates | 89 |
| `NN year-old` | 83 |
| **Surname** (`Emard`) | **0** |
| **City** (`Lowell`) | **0** |
| **Address** | **0** |
| **ZIP** | **0** |
| **SSN** | **0** |
| **Licence** | **0** |

**Synthea's notes carry a first name and dates. Nothing else.** Six of the
eight categories 3a built masks for never occur in free text at all.

**What that does to the phase.** The comparison narrows to one real question:
*can a detector find first names it was never given?* Dates are trivially
matched by a pattern, so the regex program will score near the top on them and
zero on names — and that contrast is the finding, not a disappointment. The
spec's per-category scoreboard across eight categories becomes two.

**Two bugs found in the same sitting, both of which would have been invisible
in the final numbers:**

**1. The answer sheet was missing 98% of the dates.** Built from
`silver.patient` alone it found one date per note — the birth date — while the
note holds 89. Every detector would then have been punished for correctly
finding 88 real dates. Fixed by adding `silver.encounter`; dates went from 10
to 1,351 across ten patients.

**2. The dates were off by one day.** The note says `1973-09-03`; the encounter
table says `1973-09-04`. Synthea wrote the notes in local time, but the CSV
stores UTC with a `Z`, so an evening appointment in Chicago is the next day in
UTC. Fixed with `from_utc_timestamp(started_at, 'America/Chicago')` — the same
timezone pinned in `synthea/Dockerfile` (D35).

The second is the nastier one. It cost 11% of dates overall but **94% for one
patient**, because Synthea gives each patient a consistent appointment hour, so
the error clusters by patient instead of averaging out. A spot check of one
well-behaved patient would have shown 88 of 89 and looked fine.

Date coverage after both fixes: **1,567 of 1,567 date-shaped strings, 100%**.

**Why this justifies doing step 3 before step 1.** None of it needed the notes
uploaded. Had it been found later, the answer sheet, every detector's score and
the MLflow history would all have been rebuilt — after spending 370 MB of quota.

### D51 — the name-finding model: the right one is correct and too slow

P5 could not be answered from SQL, so the notebooks were submitted as job runs
with `databricks jobs submit` — the same `runs/submit` route proved in
[D33](#d33). Two practical notes for anyone repeating this: Git Bash rewrites
`/Users/...` into a Windows path, so `MSYS_NO_PATHCONV=1` is needed on every
`databricks workspace` call; and a notebook's printed output is **not**
returned by the jobs API. Without a closing `dbutils.notebook.exit(json)` a
command-line run tells you only that it finished, which is the least useful
thing it could say. The first P5 run had to be repeated for exactly that.

**P5 — `dslim/bert-base-NER`, trained on news text.** 1.28s per piece, and the
"names" it returned were `Yu`, `Co`, `##dicare`. Wordpiece fragments. It found
37 things and none of them were a patient.

**P5b — the comparison that mattered.** The measure is not how many names a
model finds but **whether it finds the real patient's first name**, so the
probe selected pieces already known to contain it and asked exactly that.

| Model | s/piece | Hours for 41,592 | Real name found |
|---|---:|---:|---|
| `obi/deid_roberta_i2b2` | 4.16 | **48.1** | **20/20** |
| `dslim/bert-base-NER` | 1.26 | 14.5 | 8/20 |

`obi/deid_roberta_i2b2` is trained on i2b2 de-identification data — clinical
notes labelled for this exact task. It returns `Yuette` where the news model
returns `Yu`, which is the whole difference: one is a name, the other is a
fragment that would redact three characters and leave the rest in place.

**So the correct model costs 48 hours on a CPU** and the affordable one has
0.4 recall on the only thing that matters. That is the real constraint on
stage 2, and it is a Free Edition constraint — no GPU — not a flaw in the
approach.

**Hugging Face downloads work.** The spec assumed outbound internet was
restricted enough to force in-platform models. Both models downloaded without
trouble, which widens the options for stage 2 beyond what §4.3 planned for.

**P5c — batching does not help.** The 4.16s came from a Python loop, and
transformers batches on CPU, so this looked like the obvious lever:

| Batch size | s/piece | Hours for 41,592 |
|---:|---:|---:|
| 1 | 3.96 | 45.7 |
| 8 | 3.89 | 45.0 |
| 32 | 4.05 | 46.8 |

Nothing. The CPU is already saturated, so grouping the work changes only how
it is queued. Batch 32 is marginally *worse*, which is memory pressure.

**The test set has to shrink, and it must shrink for every stage, not just
stage 2.** The language model has the same problem from a different direction:
41,592 `ai_query` calls at roughly 2s each is another 23 hours. Shrinking only
the stage that is slow would score the stages on different data and make the
comparison meaningless — which is the one thing this phase exists to avoid.

**Recommended: 25 patients, about 5,200 pieces.** Stage 2 lands near 5.6
hours and stage 3 near 3 — both overnight jobs rather than impossible ones.
The sample is still large: a first name appears roughly 89 times per note, so
25 patients gives about 2,200 name occurrences and a similar number of dates.
Per-category recall is measured on thousands of instances, not dozens.

**What this costs, said plainly.** The spec asked for per-note F1 across the
corpus. It will be per-note F1 across 25 notes. That is a real reduction and
it belongs next to every number reported, not in a footnote.

### D52 — the answer sheet, built: two of its assumptions measured and dropped

`silver.phi_span` holds **439,651 positions** across all 1,148 patients:
249,887 names, 187,540 dates, 2,224 ages over 89. No patient has zero, no
position is recorded twice, and the `surface_text` column is masked for
anyone without clearance (0 → 439,651 → 0 masked rows when clearance was
removed and restored).

**The ambiguous-name ceiling is 0.3%, not a ceiling.** Step 3 planned to count
surnames that are also ordinary words (`Gray`, `Young`) from a hand-typed list
of 17, because a program that finds "gray hair" is wrong through no fault of
its own. A hand-typed list only finds the ambiguity you thought of, so the
notes themselves were used as the dictionary instead: a name value is ordinary
if it also appears lower-case anywhere in 370 MB of clinical text. Three of
1,159 name values are — `Alpha`, `Ward`, `Manual` — covering 641 of 249,887
name positions. Surnames were never the risk, because [D50](#d50) showed the
notes contain first names only. Every later score can be read as if the
ceiling were 100%.

**Dates are solved before any program runs.** Every one of the 187,540
date-shaped strings in every note is a real patient date — birth, death or
visit — with no exceptions. So any program that tags "anything shaped like a
date" scores perfect recall and perfect precision on dates. That is a property
of Synthea (its notes contain no other dates: no "last updated", no drug
approval years), not an achievement of the regex, and it must be said next to
the regex program's date score. Real notes would not be this kind. The
phase's only open question is now names.

**The 3-character minimum is gone.** It was written so that a value like `Mr`
would not match every line. It never met a value like that; it met seven
two-letter first names, whose 1,898 occurrences all sit in their own patient's
note and **zero** times in anyone else's. Whole-word, case-sensitive matching
was already the guard. The rule's only effect was to leave real names off the
answer sheet, which would have marked every program wrong for finding them —
see [E41](errors.md#e41).

**Correction to D50.** The notes usually carry only the first name, but one
patient's note writes first and middle together (`[FIRST] [MIDDLE] is a 50
year-old…`), 198 times. Synthea appears to treat it as a double first name.
The answer sheet catches it because `MIDDLE` is already searched.

### D53 — step 4 and 5: the language model wins on names, and the rest is false alarms

All four programs were run on the 25 test patients and marked by
`sql/score_detection.sql` (corrected in errors.md E45).

| Program | Name recall | Name precision | Date recall | Date precision |
|---|---:|---:|---:|---:|
| 0 — look up and search | 1.000 | 1.000 | 1.000 | 1.000 |
| 1 — pattern matching | — | — | 1.000 | 1.000 |
| 2 — name model (`obi/deid_roberta_i2b2`) | 0.913 | 0.960 | 0.994 | 0.973 |
| 3 — language model (Llama 3.3 70B) | **0.996** | 0.998 | 0.996 | 0.999 |

**Program 0 is not a result.** It is the answer sheet, and its 1.000 proves
the marking works. **Program 1's perfect dates are not to its credit**: every
date-shaped string in these notes is a real date (D52). It finds no names.

**The real comparison is 2 against 3, on names.** The language model misses
20 of 4,956 names; the name model misses 431. For de-identification that is
the only column that matters — a miss is a real name left in a document.

**What they also flag, which is not private here** (no real items of that
kind in the test set, so every one is a false alarm):

| | Language model | Name model | Pattern matching |
|---|---:|---:|---:|
| Ages (all under 90) | 6,908 | 6,876 | — |
| "Identifiers" (insurers: Medicare, Humana…) | 3,574 | 827 | — |
| "Places" (e.g. "hispanic white") | 516 | 2,463 | — |
| "ZIP codes" (drug doses: `0.00354 mg/hr`) | — | — | 889 |

Redacting those does no privacy harm and some readability harm; it is the
cost side of the trade.

**How each ran, and what it cost.**

- **Language model:** one `ai_query` statement per patient, so the calls ran
  in parallel. 5,263 pieces in ~25 minutes, not the 2.9 hours planned. 24
  replies closed their JSON with `)` and were counted as finding nothing;
  34 returned some text not in the piece word for word. Left strict: a
  repaired reply is the parser's success, not the model's.
- **Name model:** started on Databricks, stopped two hours in by Free
  Edition's usage cap (E44), finished on the laptop in ~6.5 hours at 4.5 s
  per piece. **71% of pieces were longer than the model's 512-token limit**,
  so each is read in overlapping windows. The P5 probes (D51) fed whole
  pieces to a pipeline and may have been measuring cut-off text; the 20/20
  there should be read with that in mind.

**Limits of these numbers, said where they are.** 25 notes, not the corpus
(D51). No ages over 89 in the test set, so the one age rule Safe Harbor has is
untested. And Synthea notes are an easy case — first names only, one date
format, no other people named — so both models' name recall here is a ceiling
for real notes, not a forecast.

### D54 — what counts as "found": whole coverage, not overlap or exact match

The plan asked for exact and overlap scores side by side, one chosen with a
reason. Both turned out to measure the wrong thing, so a third was added.

| Program | overlap | **covered** | exact |
|---|---:|---:|---:|
| Language model, names | 0.996 | **0.996** | 0.758 |
| Name model, names | 0.913 | **0.860** | 0.623 |
| Language model, dates | 0.996 | **0.996** | 0.996 |
| Name model, dates | 0.994 | **0.952** | 0.310 |

- **Overlap is too generous.** A guess of `Luc` inside `Lucius` counts as a
  hit and leaves `ius` in the document. The name model's 0.913 includes about
  5% of names it only partly covered.
- **Exact is too strict.** It marks `Babara Isadora`, one guess over two real
  names, as a miss on both, and that guess hides them perfectly. The
  language model's 0.758 is almost entirely this.
- **Covered** (one guess spans the whole real item) is what
  de-identification needs. It is the headline number everywhere.

It is a slight under-count: a name hidden by two adjacent guesses, neither
covering it alone, is scored as a miss. Merging per kind (errors E46) made
that rare.

### D55 — the de-identified copy: three changes to the plan, and what it is not

**The plan's date shift was reversible.** It computed each patient's shift as
`hash(patient_id) % 364` and kept `patient_id` in the copy. The formula is in
a public repo, so anyone holding the copy could compute every shift and undo
it. Instead `ops.deid_key` holds a random shift and a new random `deid_id`
per patient, drawn once and kept (a rerun adds keys only for new patients).
The copy carries `deid_id` only. That table is the whole re-identification
risk, and it never leaves `ops`.

**Full dates stay out of the patient table.** Birth and death became 5-year
bands (D56), blank for anyone over 89. Encounter and note dates are *shifted*
instead, because phase 4's readmission work needs the gaps between visits.
**Shifting is not Safe Harbor**, which permits the year only. It is the
standard research compromise, and a year-only copy would make 30-day
readmission impossible to compute.

**Notes are redacted with the patient's own details, not a model.** Here the
patient is known and Program 0 scored 1.000; the models answer a different
question: what to do when you do not have that list. What this misses is
anything not in the patient record: a relative's name, a clinician's.
Synthea's notes contain none (D50). Real notes would, and the language model
is what would catch them.

**Checked, each check shown able to fail:**

| Check | Result |
|---|---|
| Keys | 1,148, none duplicated, shifts 1-364 days |
| Every gap between consecutive visits unchanged | 0 of 1,148 patients changed |
| Patient's first name still in their note | 0 of 1,148 (the same check on the original notes: 1,148) |
| Dates moved, none lost | 187,540 before, 187,540 after |

The plan's timing check compared only the first-to-last span per patient,
which a shift applied per row could pass by luck. The check here compares
every gap in order.

The redaction function stops the build if the text at an answer-sheet
position is not what the answer sheet says. Positions were measured on the
laptop's copy of each note; one differing character would have garbled every
replacement silently.

### D56 — k-anonymity: Safe Harbor left 467 people alone; 5-year bands, no ZIP, k >= 5

`k` is how many people share a combination an outsider could know. Measured
on birth, ZIP and gender:

| Detail kept | Alone (k = 1) | Fewer than 5 share it |
|---|---:|---:|
| Full birth date + ZIP3 + gender (the plan) | 912 of 1,148 | 1,099 |
| Birth year + ZIP3 + gender (Safe Harbor) | 467 | 1,057 |
| Released: 5-year bands, gender, death band, no ZIP | **0** | **0** |

**Safe Harbor is a list of fields to remove, not a guarantee.** Doing exactly
what it permits left 41% of people unique. The 3-digit ZIP did most of the
damage, and in a one-state dataset it tells an analyst almost nothing, so it
was dropped.

**Death year counts.** With it, 128 people were alone who were not without
it, so the check groups on birth band, gender and death band together.

**Cut-off: k >= 5**, the usual threshold for record-level research data. The
cost, measured before choosing:

| Bands | People to blank |
|---|---:|
| Exact year | 309 (27%) |
| **5-year** | **143 (12%)** |
| 10-year | 83 (7%) |

Five-year bands are the standard epidemiology age grouping, so age can still
be adjusted for. Ten-year bands would blank fewer people but halve the age
resolution for everyone. The 143 keep every other column; they lose only
their birth and death bands, and then share one large group.

**Not covered, said plainly.** Race, ethnicity, marital status and income
were not counted as things an outsider could know. Income and healthcare
spend are near-unique per person: anyone who knew someone's exact income
could find them. Treating those as identifiers means rounding or dropping
them, which is the next step if this copy were ever released beyond the
workspace.

### D57 — gold: what the probes found before any table was built

Seven probes ran before step 1. Three changed the plan.

| Probe | Found | Changed |
|---|---|---|
| Can gold read the governed `silver.patient`? | 1,148 rows, 0 masked names | Nothing; the pipeline reads as a cleared user. `'***'` is the mask's real output, so the check could have failed |
| Overlapping hospital stays | 122 of 1,292 start before the last ended; 97 start the day it ended | Merging into stays is needed |
| Coronary heart disease `53741008` | **0 patients** | Statin group uses ischemic heart disease, history of bypass, history of and acute heart attack, and stroke instead |
| Diabetes `44054006` | 79 patients; **87 more** have only a complication "due to type 2 diabetes" | The 7 complication codes join the diabetes group |
| Nystatin (antifungal, contains "statin") | **0 patients** | The whole-word statin rule stays, but its check cannot fail on this data and was never exercised |
| Data end | 2026-08-08 | Care gaps measured for 2025 |
| FHIR encounter ids | 14 of 14 found in silver | FHIR reconciles on id, not patient + time |

**Planned stays** (a return for one is not a readmission): sterilization,
waiting for a kidney transplant, and sleep disorder, taken to be an
overnight sleep study, which is an assumption about Synthea, not something
the data shows. **Cancer stays count as unplanned.** A chemotherapy stay is
planned and a complication is not, and the admission reason cannot tell them
apart. Checking the stay's procedures would; it was left out as the smaller
error.

**Two checks added to the plan's, both able to fail.** Each reference table
holds one row per id (bronze keeps every file it took in, and a file loaded
twice would double every visit joined to it). No insurer paid more than the
bill. A third, "paid + covered = total", was dropped: `patient_paid` is
defined as the difference, so it could never fail.

**Money totals match to the cent** (599,866,684.50 in both), not merely
within the few cents rounding was expected to cost: Synthea's costs already
have two decimal places.

### D58 — readmissions: 15.97% became 17.54%, and each change accounted for

> **Amended by D64:** chemotherapy stays are planned and not index stays; the table is now 17 of 866 = 1.96%.

`gold.readmission_events` has one row per hospital **stay**, not per
encounter, with every exclusion as its own column. Proven in four checks:

- **A.** The phase 1 gate, rerun on today's CSVs: 1,292 encounters, 24
  died, 3 too little follow-up, 1,265 index, 202 readmitted, 15.97%.
- **B.** The gate's rules rewritten on silver: **identical**, all five
  numbers. No hospital encounter is in quarantine. So the DuckDB-to-Spark
  translation changed nothing, and every later difference is a rule.
- **C.** Each change switched on one at a time (`sql/readmission_ladder.sql`):

| Step | Index stays | Readmitted | Rate |
|---|---:|---:|---:|
| B · the gate | 1,265 | 202 | 15.97% |
| + merge overlapping and same-day encounters into stays | 1,144 | 202 | 17.66% |
| + calendar days in Chicago, not UTC | 1,145 | 202 | 17.64% |
| + data ends at the last visit of any kind | 1,146 | 202 | 17.63% |
| + a planned return does not count = **the table** | **1,146** | **201** | **17.54%** |
| Discharged to hospice | 0 stays | | |

- **D.** The patient with the most merged encounters, checked by hand
  against silver: three August 2025 encounters, each starting before the
  last ended, are one stay; the gaps to the stays either side (2,017 and 128
  days) are right.

**Merging moved the rate by pushing the denominator down, not the numerator
up.** The plan expected transfers to hide readmissions. Instead the count of
readmissions did not move; what went was 121 "index admissions" that were
really the middle of one stay. In the gate each of those counted as a
patient who did not come back, which pulled the rate down. 122 encounters
merged away: 52 stays of two, 35 of three.

**Two changes to the plan's SQL.** The first encounter of a stay is chosen
by start time *then id*: a tie broken at random could differ between SQL and
PySpark (step 7) for no real reason. And a stay is planned by the reason it
*began* with; the plan marked it planned if any encounter in it was, which
would let an emergency that merged with a sterilization stop counting.

The local-day, data-end and planned rules each moved one stay. They are
right, and small here; they are not free on a real hospital's data.

### D59 — care gaps for 2025: two measures plausible, one is Synthea's rule

`gold.care_gap` has one row per patient, measure and year; `measure_code`
holds every code the measures use (chosen in D57).

| Measure | In the group | Excluded: age / died / hospice | Eligible | Met | Gaps | Met |
|---|---:|---:|---:|---:|---:|---:|
| Blood pressure under 140/90 | 210 | 6 / 5 / 12 | 191 | 133 | 58 | 69.6% |
| Diabetics with an HbA1c test | 120 | 26 / 3 / 7 | 86 | 69 | 17 | 80.2% |
| Heart patients on a statin | 158 | 49 / 4 / 10 | 99 | 98 | 1 | **99.0%** |

**Read the statin figure as the generator's rule, not a finding.** Synthea's
heart-disease module prescribes a statin as part of the treatment it
simulates, so 99% says how the data was made. The one gap is genuine
(ischemic heart disease and bypass surgery since 2019, never a statin).
Blood pressure and HbA1c land where real-world rates do, which is also what
the generator was tuned to; neither is evidence about care.

**One change to the plan: the group starts with people alive on 1 January.**
Synthea rarely closes a diagnosis, so the plan's rule ("had the condition
during the year") put everyone who ever died with one into 2025's group, as
"excluded: died". That would have been 57, 42 and 48 extra people per
measure, and an exclusion column counting mostly the long dead. The died
column now means died *during* 2025.

**The statin rule is checked both ways.** Nystatin counted: 0, but no
nystatin exists in this data, so that check cannot fail here (D57). A
"statin" medication the rule misses: 0 of 1,985. That one can fail, and
would the day a brand not in `measure_code` appears.

Age bands are the HEDIS ones, simplified: diabetes 18-75, blood pressure
18-85, statins 21-75. The statin band is why 49 heart patients are out on
age alone.

### D60 — patient_360: one row per patient that adds up to the rest of gold

1,148 rows, one per patient, and every total equals the table it summarises:
187,540 visits and 599,866,684.50 in claims (`fact_encounter`), 201
readmissions (`readmission_events`). No age is missing; the oldest shows as
90, meaning 90 or over.

**Visits and cost come from `fact_encounter`, not silver** (a change to the
plan). Its money is already DECIMAL, so the two tables agree to the cent and
the PySpark version (step 7) starts from the same numbers.

**What it leaves out, on purpose:** name, address, every identifier number,
exact birth and death dates (only a capped age and a yes/no for deceased),
and income and healthcare spend, which D56 found close to unique per person.
Gender, race, ethnicity and marital status stay; none is a Safe Harbor
identifier. Visit dates are still exact in `fact_encounter` and
`readmission_events` (plan decision D-e): **gold is as private as silver,
and is only ever published as counts.**

After the build the drift check was clean: no tagged column unmasked, and
`silver.patient` still has all 19 tags. Gold has none. Materialized views do
not inherit tags, so "gold has no tags" is true by construction today; the
check is there for the day someone tags a gold column and a schema mask
starts rewriting it.

### D61 — FHIR flattened for the 25 test patients: identical to the CSVs

`notebooks/fhir_flatten.py` turns the 25 test patients' FHIR bundles (316
MB; the full 12.8 GB would hit the compute cap) into `ops.fhir_encounter`
and `ops.fhir_condition`, then compares them with silver, both directions:

| | FHIR | Silver | Only in FHIR | Only in silver |
|---|---:|---:|---:|---:|
| Encounters: id, patient, start, end | 4,362 | 4,362 | 0 | 0 |
| Conditions: patient, visit, code, onset, resolved | 2,426 | 2,426 | 0 | 0 |

Two exports of one simulation agreeing is what should happen, so the value is
in what the comparison forced to be right:

- **Each resource type is parsed with its own stated schema** (errors E48).
  One schema inferred across 20 resource types turned `type` into text.
- **Visit times compared as instants.** FHIR writes `-05:00`/`-06:00`, the
  CSV writes UTC; converted to timestamps they are the same moment.
- **Diagnosis dates taken as written**, not converted to UTC first, which
  would move late-evening dates a day (the D50 trap). The plan's code
  converted; whether that would have shown up here was not tested.

**Three changes to the plan, for privacy.** The bundles are uploaded named
by patient id: Synthea names each file after the patient, and uploaded as-is
25 real names would be paths in the lakehouse. Patient resources are never
parsed; only Encounter and Condition are. The comparison also covers
`resolved_date`, which the plan left out.

### D62 — two engines, one answer: PySpark matches SQL row for row

`notebooks/gold_pyspark.py` builds `readmission_events` and `patient_360`
again with the DataFrame API, into `ops.pyspark_*` (never `gold`, so no one
reads the wrong one). `notebooks/reconcile_gold.py` compares each pair with
`exceptAll` in both directions and appends the result to
`ops.reconciliation_results`.

| Table | SQL rows | PySpark rows | Only in SQL | Only in PySpark |
|---|---:|---:|---:|---:|
| `readmission_events` | 1,170 | 1,170 | **0** | **0** |
| `patient_360` | 1,148 | 1,148 | **0** | **0** |

Zero on the first run. **How much that proves, said plainly:** the stay
numbering was written first, from the plan's skeleton; the rest was written
by someone who had already written the SQL. That is a second implementation
of the same rules, not an independent reading of them, so it catches
translation slips (a wrong join type, a NULL handled differently, a type
that drifted) better than it catches a rule both sides got wrong. The rules
themselves were proven against the phase 1 gate (D58).

**What had to be pinned down for the comparison to mean anything**, each of
which would otherwise have reported differences that were not bugs:

- ties broken by start time then id, in both (D58);
- money summed from `fact_encounter`'s DECIMAL, so the total is
  `decimal(24,2)` on both sides (a summed DECIMAL(14,2) widens);
- column names and types compared, not nullability: a PySpark `count()` is
  NOT NULL where the pipeline's column is nullable;
- both sessions in UTC (the notebook reports `Etc/UTC`), with Chicago days
  made explicitly by `from_utc_timestamp` in both.

**Timings, one run each, 1,148 patients, serverless.** Not a ranking.

| | Pipeline (SQL) | Notebook (PySpark) |
|---|---:|---:|
| `readmission_events` | ~15 s for the table; 99 s for the whole update | 75.1 s |
| `patient_360` | ~9 s for the table; 83 s for the whole update | 19.4 s |

The two columns do not measure the same thing. The pipeline's per-table time
excludes starting the update; the notebook's includes its first reads and
writing a Delta table, and its job took 2.3 minutes with start-up. At this
size start-up dominates both. The spec asked for main-tier timings too;
those were not run (plan decision D-d: a day's quota).

The query plans stored in `ops.reconciliation_results` are of *reading* the
two finished tables, so they are table scans on both sides and say nothing
about how each engine built them. Comparing build plans would mean capturing
them inside the pipeline and the notebook; not done.

### D63 — the gold numbers in the app: counts per measure only

`scripts/publish_snapshot.py` adds `GOLD_SNAPSHOTS`: one row of readmission
counts and one row per care-gap measure, written to
`snapshots/gold_readmission.parquet` and `gold_care_gap.parquet`. The guard
(`check_only_categories`) now also knows the three measure names and refuses
any other text; a test proves it refuses a name. `app/pages/3_Quality_measures.py`
shows the rate, every exclusion, and the three care-gap rates with the
caveat that they describe Synthea's rules, not care.

Gold holds exact visit dates (plan decision D-e), so nothing per patient or
per stay leaves it: the snapshot is aggregates over the whole population.

### D64 — readmissions, amended: chemotherapy is planned, so 17.54% became 1.96%

Phase 5's first look at `gold.readmission_signals` found that **184 of the
201 readmissions belonged to 10 lung cancer patients**. Every inpatient
lung cancer encounter is "Combined chemotherapy and radiation therapy"
(1,599 procedures), and those patients came back every 23-27 days (median
25). Synthea's lung cancer module schedules the cycles. They were scheduled
treatment, not relapses.

D58's planned rule could not see them: it reads the reason a stay began, and
`planned_reason.sql` already said cancer was left out because the reason
cannot tell chemotherapy from a complication. The procedure can. CMS treats
maintenance chemotherapy as always planned, and its readmission measures
also leave cancer-treatment stays out of the index stays.

**The change** (user's choice, both parts):
- `gold.planned_procedure` holds the codes: `703423002` (combined chemo and
  radiation) and `367336001` (chemotherapy). It is the one place they are
  defined, like `measure_code`.
- A stay that includes one of those procedures is **planned**, whatever its
  admit reason. A return for cancer treatment is not a readmission.
- The same stay is **not an index stay**, through a new exclusion column,
  `excl_cancer_treatment`. Every exclusion stays visible.

**The ladder** (`sql/readmission_ladder.sql`) gains two steps, each switched
on alone:

| Step | Index stays | Readmitted | Rate |
|---|---:|---:|---:|
| v5 · D58's table | 1,146 | 201 | 17.54% |
| v6 + a cancer-treatment stay is planned | 1,146 | 17 | 1.48% |
| v7 + it cannot start a window either = **the table** | **866** | **17** | **1.96%** |

v7 excludes 280 stays. The 17 readmissions belong to **17 different
patients**, one each.

**Both engines agree.** `notebooks/gold_pyspark.py` got the same rule, and
`reconcile_gold.py` reports 0 rows only in SQL and 0 only in PySpark, for
`readmission_events` (1,170) and `patient_360` (1,148). `check_gold.sql`
check C now shows the new exclusion. `patient_360.readmissions_30d` sums to
17.

**What it does to phase 5.** The story's first chapter becomes "smaller
than it looked". With 17 readmissions from 17 people, spec §5's rule (at
least 10 different readmitted patients on the higher side of a split) can
hardly be met, so NO-GO is the likely result, and the spec already says
what phase 6 does then. Page 3 and the README still show 17.54% until the
phase 5 snapshot and write-up replace them.

### D65 — a second Synthea batch: 11,432 more patients beside the first

After D64 there were 17 readmissions from 17 people. That is too few for
phase 5's go/no-go rule (at least 10 readmitted patients on the higher side
of a split) or for a phase 6 model. The number of events grows with the
number of patients, so a second population was generated and landed
**beside** batch 1. Batch 1 is never regenerated.

**How.**
- **Seeds:** `-p 10000 -s 67890 -cs 12345 -r 20260101 -e 20260808 Massachusetts`.
  The new population seed gives new people. The same clinician seed gives
  the same doctors. The same dates keep both batches on one calendar.
- **CSV only, and only the 12 uploaded files:** no FHIR (about 120 GB at
  this size) and no notes.
- **Run:** 32 minutes on the laptop, 5.9 GB.
- **Spike first** (20 and 244 patients):
  - patient ids never collide;
  - payers are all shared;
  - 78 of 85 hospitals and doctors are shared.
- **Reference rows:** `scripts/new_reference_rows.py` keeps only the ids
  batch 1 lacks (321 hospitals, 321 doctors, 0 payers), so a shared id
  keeps batch 1's row. Every batch 2 visit's hospital, doctor and payer
  exists in one batch or the other.
- **Upload:** `upload.ps1 -Suffix b2` lands `<entity>/<entity>_b2.csv` next
  to batch 1's file. Auto Loader reads only the new files, so one normal
  update added them, with no full refresh: 8 minutes.
- **Telling the batches apart:** `_batch_id` is `manual` for both, because
  the pipeline config is per bundle, not per update. `_source_file` names
  the `_b2` file instead.

**What stays batch 1 only:** phase 3b's notes, held-out patients and
detection scores (`detect_llm.py` reads only `ops.heldout_patient`), and the
25-patient FHIR sample (D61). `silver.note_chunk` covers batch 1's 1,148
patients.

**Before and after.** Every check in `check_gold.sql` passes on both
batches: no unknown or duplicate reference ids, gold equals silver, and
every `_must_be_0` is 0. SQL and PySpark reconcile with 0 differences
(14,313 stays, 12,580 patients).

| | Batch 1 | Both batches |
|---|---:|---:|
| Patients | 1,148 | 12,580 |
| Visits | 187,540 | 2,074,520 |
| Hospital stays | 1,170 | 14,313 |
| Excluded: cancer treatment | 280 | 3,402 |
| Index stays | 866 | 10,724 |
| 30-day readmissions | 17 (17 patients) | **173 (158 patients, at most 3 each)** |
| Readmission rate | 1.96% | 1.61% |
| BP under 140/90 | 69.6% | 67.0% |
| Diabetics with an HbA1c test | 80.2% | 82.9% |
| Heart patients on a statin | 99.0% | 97.7% |

The ladder runs on both batches. The gate's rule gives 12.31%, and v7, the
table, gives 1.61%. **The decision.md entries before D65 give batch 1
numbers**; they are not rewritten, because each recorded what was true when
it was made.

### D66 — small cells: readmission counts of 1-10 are hidden too, and so is the level that would give them back

The spec hid a signal level only when it had **fewer than 11 index stays**.
On the real data no level is that small (the smallest is 96 stays), so the
rule hid nothing, while admit-reason counts of 1-10 readmitted would have
been published. The public health rule the spec cites hides any count from
1 to 10, and that includes the number with the outcome.

**The rule now** (`readmission_story.level_row` and `complete_suppression`):
- A level is hidden when its stays **or its readmissions**, or the rest's,
  number 1 to 10. Zero is published: it points at no one.
- A hidden level loses its **rate** as well as its counts, because
  rate × stays gives the count back.
- **Complementary suppression.** A signal's levels add up to the published
  total (173), so a signal with exactly one hidden level would give it back
  by subtraction (total − a − b = the hidden count). Its smallest published level is
  hidden with it, preferring one that has readmissions.
- The go/no-go decision (`separates`) is still computed on the real counts,
  and published for every level. Hiding changes what is shown, never the
  verdict.

**What it costs**, on the real counts: 10 of the 30 non-year levels are
hidden: age 18-44 and 80+, four of the six admit reasons, both `is_planned`
levels, and prior stays `1` and `2+`. The 0 vs 1+ prior-stay comparison
survives, as the `0` row's rest. Hiding the
numbers of low-rate levels is the price. The data is synthetic, but the
project says it suppresses small cells, and now it does.

### D67 — text-to-SQL on the dev set: the metrics note rewritten; no semantic search; no gate change

**dev-1** (`raw`, `metrics`; 20 dev questions each): raw 10 of 20, metrics
9 of 20. Every failure was sorted by cause:

| Cause | raw | metrics |
|---|---:|---:|
| wrong code | 0 | 0 |
| wrong table or column | 7 | 0 |
| MEASURE() misuse | 0 | 4 |
| every dimension selected when one number was asked | 0 | 3 |
| grouped where a filter was asked | 0 | 2 |
| should-refuse answered | 2 | 1 |
| other (summed a boolean; `other` ranked as an admit reason) | 1 | 1 |
| false block | 0 | 0 |

**Semantic search over codes is not built** (spec §8): "wrong code" was 0
of raw's 10 failures and 0 of metrics' 11, against the bar of a third. The
questions are about prepared columns, never about raw codes.

**The gate is unchanged.** Its one block (`avg_if`) was right: no such
function exists on Databricks.

**The metrics note was rewritten** (Task 7 Step 7). The old note said
"Select dimensions by name ... and GROUP BY the dimensions", which reads as
"always select them", and never said what `MEASURE()` accepts. The model
did exactly that: every dimension in the SELECT (1,000+ rows for a single
total), and `MEASURE(ROUND(...))`, `MEASURE(<expression>)`,
`SUM(MEASURE(...))`. The new note says `MEASURE()` takes only a measure's
name, a dimension is selected only to break a number down, and a filter is
a `WHERE`. The view file's own header had the same wording, and an example
on the readmission view; it now points at the note. The raw prompt was not
changed: its failures were the model ignoring a clear table comment
(`readmission_signals` is "One row per index stay", yet it added
`is_index_stay`, a column of another table, six times).

**dev-2**, after the change: metrics **9 → 16**, raw **10 → 12**. Raw's
prompt did not change, so its +2 is run-to-run noise even at temperature 0
(d02 and d09 flipped). That noise is why Task 9 runs the test set twice,
and it puts metrics' +7 well clear of chance.

**Metrics' four dev-2 failures are limits of the views, not of the note:**
- d04: answers 2030 instead of refusing.
- d11: the view has only `admit_reason_group`, so `other` ranks as a
  reason (by design: the top five are computed in gold, plan P-d).
- d15: "readmitted vs not" needs the outcome as a dimension, and the
  readmission view has it only inside measures.
- d17: "0 vs at least 1 prior stays" as two columns needs two filters in
  one query, which a metric view does not do in one SELECT.

The views were not changed to fix these. They were built from the spec
before any run, and widening them to fit dev failures is what the dev set
must not be used for twice.

**Genie on the dev set** (Task 8; run `dev-1`, the same 20 questions, a
space over the two metric views with no instructions, sample questions or
example SQL): **15 of 20**. Its five failures:

| Cause | genie | Which |
|---|---:|---|
| should-refuse answered | 3 | d04 (2030) answered with the latest year; d08 (names) answered with counts by age and gender; d20 (a prediction) answered with the latest year's counts |
| view limits | 2 | d11 ranks `other` as a reason; d15 has no outcome dimension to split by |
| wrong code, MEASURE() misuse, grouping, false block | 0 | |

Genie writes correct metric-view SQL without being told how (the questions
that broke `metrics` before the note was rewritten, it got right, including
d17's two columns), but it **substitutes rather than refuses**: asked for a
year with no data, a person's name or a prediction, it answers a nearby
question instead. Only d16 (an address) was refused. No personal detail
could leak: the views hold none.

Genie's run spanned the D68 refresh: d01-d14 were scored against D65's
gold, d15-d20 against D68's. Each verdict is consistent with itself (the
answer key and Genie's SQL ran against the same table within seconds), but
the run is not one snapshot. The test runs are.

### D68 — readmissions, amended again: a return for scheduled heart surgery is planned, so 173 became 140

Tracing the story's labels (Task 12 Step 1) meant reading the Synthea
modules behind the readmissions, at the pinned commit `7e08387`. About 140
of the 173 were heart stays:

| Path | Returns | What the generator does |
|---|---:|---|
| CABG → CABG | 57 | `heart/cabg/postop`, state `Post Discharge Outcomes`: **10.6%** go to `Readmission to Ward` after 1-30 days. A real readmission, by rule. |
| abnormal heart imaging → CABG | 32 | The same rule. The surgery stay's admit reason is the pre-op encounter that opened it (`heart/cabg/cabg_referral`, `Immediate Surgical Admission`); no operation on the return day. |
| aortic valve → valve | 24 | `heart/avrr/sequence` books the `AV VHD Follow-up` as an **inpatient** stay; the valve operation follows days later. 19 of 24 returns are the operation. |
| other → CABG | 1-10 | All start the day of a CABG. The *index* stay was mostly a heart attack; the return's own reason is the bypass history, which is not acute (see D70). |
| → heart failure | 21 (18 from a heart failure stay) | `congestive_heart_failure` readmits on worsening. Real by rule. |

**A first reading was wrong**, and the data corrected it: the 32
imaging → CABG returns looked like the scheduled operation, but none has an
operation on its return day.

**The rule.** CMS treats CABG and aortic valve surgery as potentially
planned: a return for one is planned unless it is acute. So a stay with a
scheduled heart operation (`gold.planned_procedure`, kind `heart_surgery`:
232717009, 418824004, 26212005, 1155885007, 773996000) **from the day before
admission to discharge** is planned. The day before, because Synthea
records a CABG on the ambulatory visit just before the inpatient stay. An
emergency CABG (414088005, kind `emergency_heart_surgery`) in the same
window keeps it unplanned; none of the returns had one.

**Unlike D64, the surgery stay can still start a window.** D64 also took
chemotherapy stays out of the index stays. Here that would be wrong: the 57
real CABG readmissions start from the surgery stay. So `planned_procedure`
gained a `kind` column, and `excl_cancer_treatment` reads only
`cancer_treatment`.

**Before and after** (ladder v8 = the table; every `_must_be_0` is 0):

| | D65 | D68 |
|---|---:|---:|
| Index stays | 10,724 | 10,724 |
| 30-day readmissions | 173 | **140** |
| Patients readmitted | 158 | 127 (at most 3 each) |
| Rate | 1.61% (1.39-1.87) | **1.31% (1.11-1.54)** |
| Returns not counted, planned | not recorded | 48 |
| CABG admit reason | 59 of 606 | 59 of 606 |
| Story verdict | GO, 10 signals | GO, 9 signals |

Emergency visits in the year before stopped separating. The CABG
readmission rate (59 of 606, 9.7%) is the generator's 10.6%.

**What it means for phase 6.** The returns that remain are mostly
Synthea's heart modules by rule, so the signals that separate (heart
disease, age 45-79, more conditions, hypertension, diabetes, men) largely
mark who enters those modules. A model will learn that; page 4's labels say
so.

**The dev runs (D67) were scored against D65's gold.** Their verdicts are
not rerun; the test runs (Task 9) are scored against this table, because
the answer key's SQL runs at scoring time.

### D69 — phase 5: the readmission story, its go/no-go, and the text-to-SQL result

**The question.** Who comes back to hospital within 30 days, and could we
have seen it coming at discharge? Five chapters on app page 4, ending in a
signal shortlist and a go/no-go for phase 6. The text-to-SQL harness asks
the story's own questions.

**Probes** (before any table):
- **P1:** metric views work on Free Edition, `version: 1.1`.
- **P2:** Genie's API answers from a script, 14.3 s per question
  (16.4 s on the test runs). Its space id must not carry `?o=` (E49).
- **P3:** `ai_query` takes 4-7 s per call cold, 2.1-2.5 s per answer on the
  runs. `system.billing.usage` is readable but lags by hours, so cost is
  reported as seconds per answer. Two test runs fit; nothing was dropped
  for Free Edition.

**Decisions made while planning:**
- P-a: metric views are laptop SQL, not pipeline tables (definitions over gold).
- P-b: the test set's fingerprint also lives in `eval/questions_test.sha256`.
- P-c: run ids are `dev-N` or `test-N`.
- P-d: medians and the top five admit reasons are computed in gold, because
  a metric view dimension cannot see every row.
- P-e: per-level patient counts drive the rule and are never published.
- P-f: the five admit reason names are pasted into the snapshot guard.
- P-g: no MLflow task here (phase 6).
- P-h: page 3's readmission block moved to page 4.
- P-i to P-k: D64, D65, D68.

**`gold.readmission_signals`** is one row per index stay. Its column names
are the leak guard: `post_*` is known only after discharge (a follow-up
visit), `outcome_*` is the answer. Naming is not the whole guard, though:
`stay_claim_cost` is unprefixed but the bill is not final at discharge, and
`admit_year` and the keys are not features either (spec §3). The table
COMMENT lists every exclusion (D70). **Care
gaps are not a signal:** `gold.care_gap` measures 2025 alone, and stays go
back decades, so a 2025 gap on a 2012 stay would be the future. Its checks
(`check_gold.sql`): 10,724 rows and keys, 140 readmitted as in
`readmission_events`, and 0 in every `_must_be_0` (return cost, follow-up
after a return, age, cost).

**Order of work, provable from git:** the test questions were committed
(`4a22ef6`, fingerprint `718b4259...6653`) before `sql/metric_views.sql`
first was (`22267af`), so no view was shaped to them.

**The story** (all "in this synthetic data"; page 4 carries the same
sentences):

| Chapter | Finding |
|---|---|
| 1. How big? | 140 of 10,724 index stays (1.31%, 95% 1.11-1.54) come back, from 127 patients. Ladder v5 (D58's rules, before D64 and D68): 1,737 of 14,111, 12.31%; the phase 1 gate rounds to the same figure. |
| 2. Who? | Heart disease or stroke 4.06% vs 0.39%; ages 65-79 3.18%; hypertension 2.48%; diabetes 2.11%; men 1.66% vs women 1.02%; nobody under 18. |
| 3. Around the stay | Bypass history 9.74% (the generator's 10.6%). Planned stays 2.52% vs 0.79%, because bypass surgery is planned and the returns start there. Length of stay: no difference. Follow-up within 7 days 2.95% vs 1.11%: after discharge, so explanation, not prediction. |
| 4. Cost | Index stays $114.6M ($10,683 each); returns $0.51M ($3,648 each). |
| 5. Could we see it? | 9 of 11 at-discharge signals separate: **GO**. |

**Labels** (spec §4), traced in the Synthea modules at `7e08387`. Of the
140 readmissions, **91 are one rule**: `heart/cabg/postop`, state
`Post Discharge Outcomes`, sends 10.6% of bypass patients to `Readmission
to Ward` 1-30 days later. 21 more are `congestive_heart_failure`. Each
shortlisted signal was rerun by §5's rule **without those 91**:

| Signal | Label | Separates without the 91 |
|---|---|---|
| Heart disease or stroke | generator rule: heart/cabg/postop | no |
| Gender | generator rule: heart/cabg/postop | no |
| Diabetes | generator rule: heart/cabg/postop | no |
| Admit reason | generator rule (the bypass level) | yes (`other` high, drug abuse low) |
| Planned admission | generator rule, through D68 | yes, and reversed: planned is then low |
| Age band | mostly that rule; not traced | yes (18-44 low, 45-64 high) |
| Hypertension | mostly that rule; not traced | yes |
| More conditions than the median | mostly that rule; not traced | yes |
| Prior stays in the year | mostly that rule; not traced | yes (1 stay high) |

Length of stay and emergency visits do not separate; follow-up separates
but is after discharge, so it is never shortlisted.

**Phase 6 handover** (spec §10):
- **Features:** `gold.readmission_signals` **minus** `patient_id`, `stay_no`,
  `admit_year`, `stay_claim_cost` and every `post_*` and `outcome_*` column;
  target `outcome_readmitted_30d`. Build the list from these exclusions, not
  from the naming rule alone.
- **GO** by §5's rule as written: 9 signals separate.
- **Baselines to beat:** the base rate, 1.31%; and the one-rule model
  "heart disease or stroke on the admit day", which flags 25% of index
  stays (2,684) and catches 78% of readmissions (109 of 140) at 4.06%.
- **Split by patient**, never by stay.
- **Report every result twice: with and without the bypass rule's 91
  returns.** With them, a model mostly learns who has bypass surgery. Without
  them, 49 readmissions remain, which is thin; phase 6 should say so rather
  than tune on it.

**The text-to-SQL result.** 20 frozen test questions, four contestants, two
runs. The answer key scored 20 of 20 both times, so the scoring stands.

| Contestant | Tier 1 (3) | Tier 2 (5) | Tier 3 (8) | Tier 4 (4) | test-1 | test-2 |
|---|---:|---:|---:|---:|---:|---:|
| Genie + metric views | 3 | 4 | 5 | 4 | **16** | **15** |
| Llama 3.3 70B + metric views | 2 | 2 | 4 | 4 | 12 | 13 |
| Llama 3.3 70B + gold tables | 3 | 2 | 3 | 2 | 10 | 11 |

(Tier columns are test-1.) Verdicts that changed between runs: Genie 1,
metrics 2, raw 2, so a difference of 1-2 is noise. **Tier 3**, the measures
with rules: Genie 5, metrics 4, raw 3.

Test-1's failures by cause:

| Cause | raw | metrics | genie |
|---|---:|---:|---:|
| wrong table or column (`is_index_stay` from the other table, 3 times) | 4 | 0 | 0 |
| added up a boolean column | 3 | 0 | 0 |
| wrong rule (a rate's denominator; an invented "unplanned only" filter) | 1 | 1 | 0 |
| MEASURE() misuse | 0 | 1 | 0 |
| asks past what the views hold (longer than 7 days; 3+ ER visits) | 0 | 2 | 2 |
| two filtered rates as two columns | 0 | 3 | 2 |
| outcome used as a filter (not a view dimension) | 0 | 1 | 0 |
| should-refuse answered (an insurer by join; a prediction) | 2 | 0 | 0 |

**What 20 questions can say:** a semantic layer removed raw's own mistakes
(wrong tables, types) and its personal-data answers, which the views cannot
give by construction. Genie led metrics by 4 and then 2 (raw by 6 and 4):
the second run's gap is inside the noise, so Genie's lead is likely but not
firm; metrics vs raw (2 both times) is within noise.
**What they cannot say:** that the views are better in general. Two test
questions asked for detail the views do not keep, and all three
contestants missed both. That is **this layer's** cap, not every layer's:
spec §6 asked for every at-discharge column as a dimension, and the plan
built only the bands and flags, a departure no decision recorded until D70.
The metrics
prompt was improved on the dev set (D67) and raw's was not, so part of
metrics' margin is that note. Written the same way whichever way it came
out.

**Three caveats on the harness, from the final review (D70):**
- Genie writes and runs its SQL inside its own space, so for Genie the
  safety gate checks SQL that has already run. The space holds only the two
  metric views and is read-only, so the exposure is those views.
- Any Genie reply without SQL scores as a refusal; Llama must say exactly
  REFUSE. Genie's text is not stored, so its 4 of 4 on tier 4 was audited by
  asking the four questions again: all four replies said the tables hold no
  such personal detail. The score stands.
- t09 (top 3 reason groups) has no tiebreak; it is exact only while the top
  three counts differ, which they do.

### D70 — the final review of phase 5: what it found, and what changed

A fresh reviewer read the whole branch (f3cc8a7..45ae818): **0 critical, 8
important, 16 minor**. Every important finding was checked against the data
before anything changed.

| | Finding | Checked | Done |
|---|---|---|---|
| I1 | Page 4's year chart showed only years with no readmissions: every year with any had 1-10, so all 74 were hidden | true | `admit_period` in the readmission view (1915-1989, then each decade to 2020-2026; 15 to 43 readmissions each), replacing `admit_year` in the story |
| I2 | Real counts of hidden levels sat in D66 and the tests, so they could be worked out from the repo | true | made-up numbers in the tests; D66 and D68 reworded. Git history still holds them; the data is synthetic |
| I3 | "12.31% before D64 and D68" was said to be the phase 1 gate's figure | **not a defect**: ladder v5 (D58's rules, both batches) is 1,737 of 14,111 = 12.31%, and the gate rounds to the same | D69 now names v5 |
| I4 | "9 of 12" signals at discharge | true: 11 | README, D69 |
| I5 | "The unprefixed columns" as features would include `stay_claim_cost`, which spec §3 excludes | true | explicit exclusion list in D69 and the table COMMENT |
| I6 | D68's "unless acute" covers only the emergency CABG code, and the returns after a heart attack became planned | **not a defect**: CMS judges acuteness by the *return's* own reason. All 34 returns now planned were admitted for aortic valve disease, a bypass history or abnormal heart imaging; none acute | D68 says so |
| I7 | Genie's non-SQL replies score as refusals; its text is not stored | true, and **audited**: the four tier-4 test questions asked again, and all four replies declined | caveat in D69 |
| I8 | The views keep bands and flags only, against spec §6, which asked for every column; the two all-miss test questions come from that | true | recorded here and in D69 and the README; the views were not widened for the questions already asked |

**Minor findings taken:** a check that D68's day-before window never takes
a surgery from the stay before (`check_gold.sql`, 0); PySpark selects the
heart-surgery kinds by name, not by pattern; the `stays.is_planned` comment
names D64 and D68; tests for the complement's preference and for a
`post_`/`outcome_` signal never being shortlisted; `publish_snapshot` stops
before writing if any shown count is 1-10 or a signal has one hidden level
(`check_small_cells`); a NULL level stops the publish; gate messages are
scrubbed like other errors; page 4 shows both test runs; Genie's lead is
stated as "4 and then 2". **Not taken:** the follow-up check's strength
(the rule is correct by construction), a friendlier error for misspelt
question keys, and the question file's t09 tiebreak (frozen; noted in D69).

**The views changed after the test runs** (a dimension and a comment). The
recorded runs used the earlier file; a rerun would see `admit_period`,
which no question asks about.

**The Genie space was deleted after the test runs.** Nothing later needs it:
phase 6 reads gold, and the runs' verdicts are in `ops.eval_run`. To rerun the
`genie` contestant, create a new space over `healthcare_dev.metrics.stays` and
`.readmission` with no instructions, sample questions or example SQL (Task 8),
and pass its id without `?o=`.

### D71 — phase 6: the readmission model, its verdict, and the platform around it

**What was built.** The lifecycle, not a model to trust: patient-grouped
cross-validation choosing between logistic regression and gradient boosting;
every candidate, both baselines and the champion logged to MLflow; each
population's champion registered in Unity Catalog with a `champion` alias and
a `beats_rule` tag; batch scores in `ml.readmission_scores`; a drift report
appended to `ml.drift_report`; app page 5. The logic is pure Python
(`scripts/readmission_model.py`, `scripts/drift.py`) with local tests on
made-up rows; three notebooks run it as serverless jobs from the bundle's
synced folder. Spec and plan: `docs/specs/2026-10-03-phase-6-design.md`,
`docs/plans/2026-10-03-phase-6.md` (both local only).

**Probes.**
- P1: serverless runs Python 3.11.10, numpy 1.26.4 and **pandas 1.5.3** (the
  laptop has 2.2.3; the code uses nothing newer). `scripts/` imports from the
  bundle folder.
- P2: the Unity Catalog registry works on Free Edition only with MLflow
  3.16.1 installed by `%pip` **and**
  `MLFLOW_USE_DATABRICKS_SDK_MODEL_ARTIFACTS_REPO_FOR_UC=True`. The MLflow
  serverless ships was denied direct writes to catalog storage (E52), and
  ignored the switch on its own.
- P3: 14.9% of index stays had an emergency visit on the admit day or the
  day before, so `arrived_via_emergency` was kept.
- P4: one admit reason appears only from 2020, covering 7.0% of production
  stays: "Disease caused by severe acute respiratory syndrome coronavirus 2",
  that is COVID-19. The probe's `LIKE '%covid%'` missed it because the
  SNOMED name never says "covid"; corrected to `'%coronavirus%'`.

**The split** (stays / readmitted). Training is admitted by 2019 and
discharged by 1 December 2019; the gap (a few dozen 2019 stays discharged
later) is used for nothing; production is admitted from 2020. Training is
rounded and the gap left out: with the exact totals, exact training counts
would give the gap's 1-10 back by subtraction (D72).

| Population | Training | Production |
|---|---|---|
| all | about 8,200 / about 100 | 2,451 / 34 |
| without bypass surgery | about 7,700 / about 40 | 2,208 / 17 |

The populations match the spec exactly: 10,724 / 140 and 9,891 / 61.

**The verdict.** Both scorers flag the same number of production stays (868
for all, 625 without bypass, as many as the rule flags). The interval is the
model's recall minus the rule's, resampling patients 1,000 times; both flag
as many stays as the rule flags in each resample. Figures are from model
version 2, after the final review's fixes (D72).

| Population | Champion (CV average precision) | Model minus rule, median (95%) | Verdict |
|---|---|---|---|
| all | boosting, depth 3, rate 0.05 (0.142) | +12.2 points (-3.0 to +29.0) | **no better** |
| without bypass | logistic, C = 1 (0.111) | +35.7 points (+7.1 to +64.8) | **too few to judge** |

In plain words: on every index stay the model caught a few more
readmissions than the one rule, but too few to rule out luck, so the rule
stands. Without the bypass population the whole interval is above zero, but
it rests on 17 readmissions, under the 30 the spec fixed before any number
was seen, so it is not a result; it points the model's way and no further.
The recall percentages themselves are not written here or on page 5: every
model and rule row has 1-10 readmissions caught or missed (D66).

**Ranking is not calibration.** In "all" the model's average precision is
0.052, about twice the rule's, against the base rate's 0.014: it orders
stays better. (The rule's exact figure is not written: for a yes/no rule it
gives the caught count back, D72.) Its Brier score, 0.01385, is no better than the base rate's 0.01368.
Its scores are an order, not a risk to read as a probability.

**Self-returns** (P-g: a catch that is itself a stay within 30 days of an
earlier discharge): 1-10 of the model's catches in each population.

**Drift** (training against 2020-2026):
- **Shifted:** admit reason (PSI 0.62; COVID is 7% of production stays), age
  (mean 41.7 to 52.2 years, PSI 0.35), conditions at admission (mean 11.5 to
  14.8, PSI 0.36), and three true/false features by their rate: heart disease
  or stroke 21.8% to 35.4%, hypertension 23.7% to 35.3%, diabetes 15.8% to
  25.8%.
- **Watch:** bypass surgery 7.1% to 9.9%, planned admission 30.7% to 27.7%.
- **Stable:** prior stays, emergency visits, length of stay, encounters per
  stay, days since the last discharge, gender, arrival via emergency.
- **The flag rate.** The cutoff flags as many training stays as the rule
  did, about 22%, measured on out-of-fold scores (D72). Production flags
  31-36% in every year from 2020 for "all", each year's interval above 22%.
  The biggest move is at the 2020 boundary itself; after it the rate stays
  in that band. Per-year training rates were not computed, so whether the
  patients were already changing before 2020 is not shown. What is shown:
  2020-2026 patients are older and carry more chronic disease, which fits
  Synthea following people through their lives.
- **The outcome did not move measurably:** readmission rate about 1.3% to
  1.4% (all), 0.6% to 0.8% (without bypass); the intervals overlap.

**PSI under-alarms on true/false columns (P-m).** The first drift run read
heart disease going from 22% to 35% as PSI 0.09, "stable": with two values,
PSI barely moves. True/false features are now judged by their rate: if the
training rate lies inside the 95% Wilson interval of the 2020-2026 rate, it
is stable; outside it, a move of 5 points or more is shifted and anything
smaller is watch, because with about 2,450 stays a 3-point move is already
significant. (The training rate's own uncertainty is ignored; it rests on
about 8,200 stays.) PSI is still reported. Every run is in
`ml.drift_report`; the first is the "before".

**Decisions made while planning** (plan P-a to P-m):
- P-a: notebooks run from the bundle's synced folder and import `scripts/`;
  `scripts/run_notebook.sh` submits, waits and prints the exit JSON.
- P-b: scikit-learn 1.6.1 and MLflow 3.16.1 pinned; numpy 1.26.4 and scipy
  1.14.1 pinned locally too (E55).
- P-c: `ml.model_results` holds the comparison rows, so the snapshot reads
  SQL like every other page.
- P-d: `publish_model_results` hides a recall on 1-10 caught or missed, then
  drops every count; no count reaches the parquet.
- P-e: the base rate is computed (k/n), not simulated.
- P-f: the bootstrap rescales k to each resample's size (replaced in D72:
  k is the rule's own flag count in each resample).
- P-g: a self-return is `days_since_last_discharge <= 30`.
- P-h: `ml.drift_report` appends, one batch per run.
- P-i: a rate's status comes from the Wilson interval.
- P-j: the new/returning breakdown gets no bootstrap.
- P-k: feature drift is computed for "all" only.
- P-l: the drift columns are `drift_check` and `period`; `check` and
  `window` are SQL keywords.
- P-m: true/false features are judged by their rate (above).

**Rulings made while building:**
- Models are saved with skops, MLflow 3.16's default. Three named types are
  trusted (E56), not `serialization_format="pickle"`, which trusts
  everything.
- `last_discharge` groups by `admit_day` too (E54).
- The snapshot converts NULL number columns to numbers before its text guard
  (the SQL connector returns NULL as `None`).
- The plan's "18 runs" was wrong: 7 candidates, 2 baselines and 1 champion
  per population is 20.

**What phase 8 receives.**
- `ml.drift_report`, with history and a status per check. As it stands it
  would have called for a retrain from 2020: a model trained up to 2019 does
  not describe the 2020-2026 patients.
- Both registry aliases, with tags.
- Notebooks whose cutoff dates are `split()`'s parameters.

### D72 — the final review of phase 6: what it found, and what changed

A fresh reviewer read the whole branch (3f37267..e96e358): **2 critical, 3
important, 7 minor**. Each critical and important finding was checked
against the committed files or the data before anything changed.

| | Finding | Checked | Done |
|---|---|---|---|
| C1 | `model_results.parquet` gave a 1-10 count back: a breakdown's base-rate "average precision" is readmitted / stays at full precision | true: one breakdown's exact count came back from it | a new/returning breakdown publishes its verdict only, no numbers; every number is rounded to 4 places (drift to 3) |
| C2 | D71's split table gave the gap's 1-10 back by subtraction; the drift snapshot's exact training rate did the same | true | training counts rounded ("about 8,200"), the gap left out, rates in prose to one decimal |
| I3 | PSI read 0 for any count most rows share (0 prior stays): the quantile edges collapse and right-closed bins put 0, 1, 2 together | true: the planted case read 0.0 | `searchsorted(side="left")`, a zero-inflated planted-shift test; prior stays and encounters now read 0.002 and 0.015, still stable |
| I4 | The cutoff and the drift reference came from the model scoring its own training stays | true in code | both from out-of-fold scores (`oof_scores`, the same grouped folds). The flag rate is still 31-36% against 22%: the shift is real, not that gap |
| I5 | "A steady rise, not a 2020 step" was not supported | true: the biggest move is at 2020 | D71 reworded |

**A scoped re-review of these fixes found three more**, all checked and
fixed:
- **The rule's average precision and Brier gave its caught count back.**
  For a yes/no rule, average precision is c²/(R·F) + (R−c)/N, so a published
  0.0248 (and D71's "0.025") pins one caught count exactly. Both are now
  hidden wherever the rule's recall is. The model's are ranking scores and
  stay.
- **The training readmission rate**, even at 3 decimals, narrowed the gap's
  readmissions to a handful. It is no longer published; the 2020-2026 row's
  status still compares with it.
- **This entry first quoted the leaked fraction itself.** It now does not.

The MLflow screenshot in the README showed the rule rows' full-precision
average precision, so it was retaken with the champion rows only.

**Minor findings taken:** the rate rule was described backwards (D71, page
5); heart disease in training is 21.8%, not 22.0% (the first figure
included the gap); page 5 shows cross-validated average precision, as spec
section 7 asked; the logged model's pyfunc returns probabilities, matching
its signature (`pyfunc_predict_fn="predict_proba"`); the bootstrap flags as
many stays as the rule does in each resample instead of rescaling one k,
which moved the binary rule off its own count (about half a point on the
median); a test's spacing. **Noted, not changed:** `ml.readmission_scores`
keeps rows for superseded versions; a consumer filters on the champion's
version.

**Results after the fixes** (model version 2): the same champions and
verdicts. All: +12.2 points (-3.0 to +29.0), no better. Without bypass:
+35.7 points (+7.1 to +64.8), too few to judge.

**The leaked snapshot stays in the `phase-6` branch history** (commit
670644d). The branch is squash-merged into `main` and then deleted, so
`main` never holds it; the data is synthetic, as with D70.

**What the spec's own check would have missed:** section 7's "extend
`check_small_cells`" guards one column at a time. The rule that matters is
per group: a group with 1-10 readmissions publishes no number at all, and
neither does the group that gives it back by subtraction.


### D73 — phase 7: dbt cut; gold's invariants become pipeline gates

**dbt is cut, not deferred.** Each thing it would have added has a native
form in the Lakeflow pipeline:

| dbt benefit | Used instead |
|---|---|
| Tests on every build | Expectations with `ON VIOLATION FAIL UPDATE` |
| A contract on a model | A typed column list in the materialized view's `CREATE` |
| Lineage | Unity Catalog lineage; exposures stay as README prose |
| A DAG of SQL models | The pipeline already is one |

Taking gold over would have split the medallion across two tools, needed a
switch-over that drops and recreates every gold table, risked the numpy and
connector pins (E55), and changed Airflow. The case left was CV value. This
supersedes brainstorm-log §7, which stays frozen.

**What replaced it:**
- **Row gates** in the `CREATE` of the table they protect, 15 in gold: 9 on
  `readmission_signals`, 2 each on `fact_encounter` and
  `readmission_events`, 1 each on `patient_360` and `care_gap`. A row gate
  fails the update before its table is replaced.
- **22 cross-table gates** in `gold_checks`, a private materialized view:
  one row of violation counts, each `EXPECT (x <=> 0)`.
- **The silver gate** D-log called "Enforced, not trusted" was never
  attached. `unmapped_encounter_class` now has `EXPECT (false)`: any row
  fails the update.
- **The contract** on `readmission_signals`: its 29 columns declared with
  the types `DESCRIBE` reported, plus `key_copies` (added for E59). A planted wrong type failed at
  `--validate-only`, before any data was touched. A local test checks that
  every column the model reads is declared.
- `sql/check_gold.sql` is now a report. Every query that became a gate is
  replaced by a pointer to it.

**What the gates found on their first runs.** Three things, all in
`errors.md`:
- **E57:** a NULL expectation is a **violation** in Lakeflow; the spec had
  assumed the opposite. The first update failed on correct data
  (`no_followup_after_return`). Every condition is now NULL-safe.
- **E58:** the pipeline rebuilt `readmission_events` with
  `encounters_in_stay` multiplied for 3,374 cancer-treatment stays.
- **E59:** the next update rebuilt `readmission_signals` with 738 duplicate
  stays. `gold_checks` caught it, but only after the table was replaced.

E58 and E59 share a symptom: inside the pipeline, a `SELECT DISTINCT` CTE
that was joined afterwards did not remove duplicates. The same SQL built
correct tables in phase 6 and runs correctly on the warehouse. **The cause
is not established.** All three builds involved (two bad, one good) were
full recomputes, not incremental refreshes, so that explanation is ruled
out. A runtime change on channel `CURRENT` fits, but its version could not
be read to confirm. Two changes:
- `readmission_signals`, `readmission_events` and `care_gap` carry
  `key_copies` and a row gate `EXPECT (key_copies = 1)`, so a duplicated
  build fails before it replaces the table. **This is the protection.**
- The nine joined `SELECT DISTINCT` CTEs in gold are `GROUP BY` with a
  `count(*)`. It held on one build, but Spark may compile it to the same
  plan as `DISTINCT` (the unused count is pruned), so it is not relied on.
  A bug that inflates a total without duplicating keys, as E58 did, would
  still be caught only by `gold_checks`, after the table is replaced.

**Side effect on the text-to-SQL eval.** Its "gold" contestant builds its
prompt from `information_schema.columns`, which now lists `key_copies` on
three tables and a longer `readmission_signals` comment. A rerun would not
repeat the recorded gold baseline exactly; the frozen question set is
unchanged.

Nothing read the wrong tables: no model, scoring or snapshot ran while they
were wrong, and the published `encounters_merged` (1,382) is the correct
value.

**The gates' limits, said plainly:**
- `gold_checks` runs after the tables it reads. It turns a quietly wrong
  build into a failed update; it cannot roll one back (E59 is the case).
  Uniqueness, which matters most, is therefore also a row gate.
- A gate on a table the update plans as `NO_OP` is not evaluated.
  `fact_encounter`'s two gates ran once, and passed, in the update E59
  failed;
  the silver `unmapped_encounter_class` gate has not run on real data, its
  table having been `NO_OP` in every update.
- **Not tested:** the Airflow DAG turning red. Its operator waits for the
  run to finish and has `retries=0`, so it is red by construction. Testing
  it would have meant a full pipeline run just to watch a red square.

**Proof that gold did not move:**
- The fingerprint (row count and hash sum, `sql/gold_fingerprint.sql`) of
  all 12 gold tables matched the before-record, `key_copies` left out.
- `readmission_events` equals the PySpark build (`EXCEPT ALL` both ways,
  0), and `readmission_signals` equals its before-copy (0 both ways).
- So the ML side stands unchanged: champion v2, D71's verdicts,
  `ml.readmission_scores` and `ml.drift_report`. So do the snapshots.

**Each kind of gate was seen failing with its constraint named:** a row
gate for real (E57, which left `readmission_signals` at its last good
version), and a cross-table gate twice, once for real (E59) and once planted
(`unknown_organization`).

**Probe answers:** a private view with expectations works and can be
refreshed by name; a typed column list works and catches a wrong type at
validate; a failed row gate keeps the table's previous version; a pipeline
can read `information_schema`, so "gold carries no governed tag" is a gate.

**The lesson for phase 8.** Two silent runtime bugs reached gold in two
days, and only the gates caught them. The PySpark reconciliation would
have too, but it runs by hand. A retrain-on-drift DAG must not train on a
table no gate has checked.

### D74 — phase 8: the AI/BI operations dashboard

**Why.** The analytics answered "why are patients readmitted?" well, but
showed little of what an analyst job asks for: KPIs against a benchmark,
filters, trends, variation, and a "so what". One Databricks AI/BI page
closes that gap. It displaces nothing in the pipeline, and Airflow depth
and retrain-on-drift (D71's handover) move to phase 9. Its reader is a
hospital quality and operations director.

**What it shows.**
- **Tiles:** visits, stays, average length of stay and cost per stay. Each
  covers the last 12 complete months, with the 12 before it as the
  counter's comparison value.
- **The 30-day readmission rate uses D70's periods** (2020-2026 against
  2010-2019). At about 500 stays a year, 12 months would almost always hold
  1-10 readmissions, so the tile would always be hidden.
- **Care-gap closure** for three measures, for the one measure year in gold.
- **A table of changes and gaps to the network**, a visits chart by month
  and type, and length of stay and cost by quarter (monthly is noise at
  about 40 stays).
- **Payer and hospital tables**, and an executive summary of three findings
  and three recommendations, quoted only from numbers the default view
  shows.
- **No readmissions by payer or hospital.** One hospital has 11+
  readmissions, and `readmission_signals` has no payer.

**The windows are computed, never typed.** `metrics.kpi_window` takes the
last day of data (2026-08-14). The last complete month is July 2026, so the
window is Aug 2025 - Jul 2026.

**Gold: stay cost and length of stay for every stay.** They existed only
for index stays, inside `readmission_signals`, which left out the stays
that end in death, hospice or cancer treatment. The `stay_cost` logic
moved, unchanged, into `readmission_events`. That table gained
`organization_id` and `payer_id` (the first encounter's), plus
`length_of_stay_days` and `stay_claim_cost`, and three NULL-safe gates.
`readmission_signals` now reads cost and length of stay from it. **The
proof:** all 12 gold fingerprints match before and after (the four new
columns left out). `EXCEPT ALL` reads 0 both ways for `readmission_events`
against the PySpark build, and for `readmission_signals` against its
before-copy.

**The metrics layer.**
- **New views:** `metrics.operations` (visits by month, type, hospital and
  payer) and `metrics.care_gaps`.
- **`metrics.stays` gained** month, quarter, hospital and payer, plus
  `stay_cost`, `cost_per_stay` and `avg_length_of_stay_days`. Its old
  numbers are unchanged.
- **Joins work on Free Edition.** Hospital and payer come in as star joins
  (`joins:`) in the metric views (probe c). The new `check_metrics.sql`
  checks show every visit, stay and dollar counted once after the joins,
  with none unnamed.

**The privacy rule.** It is wider than D66: any count of 1-10, and any
number over a group of 1-10, is NULL.
- **One function, nested.** `metrics.shown(n, value)` returns NULL when
  `n` is 1-10 or unknown. A number that depends on several counts nests
  one `shown()` per count. A rate is
  `shown(numerator, shown(rest_of_group, rate))`, which also stops a rate
  plus a visible group size from giving a small count back.
- **Filters are query parameters,** not dashboard filters, so the rule sees
  the filtered group.
- **Secondary suppression, in the payer table only (E61).** It sits beside
  its own total, so it hides the fewest further payers that leave a hidden
  one free to hold anything from 1 to 10 stays (a protection interval). On
  the default view that is five of ten payers. Checked on the default view:
  - the hospital table's leftover is not 1-10;
  - the visits chart and the quarterly stays chart have no hidden cell.

  No other dataset carries secondary suppression.
- **What the test checks.** `tests/test_dashboard_privacy.py` reads the
  exported dashboard. It checks:
  - each returned number is one `shown()` call;
  - each dataset applies the filters it must (comments stripped);
  - nothing wraps the query after `FROM final`;
  - `by_payer` keeps `privacy_n`;
  - no widget re-aggregates rows.

  It does not check that the count passed to `shown()` is the right one.
  That rests on review.
- **The boundary.** Inside the dashboard, which is private behind the
  workspace login, recovering a hidden cell by comparing two filtered views
  is accepted. Choosing one of the protective payers, for example, shows its
  own count. The public outputs (the README screenshot and summary) show the
  default network view only.
- **The filter check (spec §7) was run in SQL,** not in the UI: choosing the
  small payer turns the stay tiles NULL.

**The dashboard is code.**
- It was built through the Lakeview API from the plan's SQL, then exported
  with `bundle generate dashboard`, bound with `bundle deployment bind`, and
  deployed by `bundle deploy -t dev`.
- `parent_path` pins its folder. Without it, the deploy wanted to delete and
  recreate the dashboard with a new id and URL (E62).
- After a UI edit, re-export before committing, or the next deploy
  overwrites the edit.
- The executive summary was added by editing the JSON and deploying it.
- Databricks showed an "Automated browser control detected" banner during
  the visual check, so later visual checks are by hand.

**Probes.**
- **a:** the data ends mid-month (2026-08-14).
- **b:** the counter has a comparison value.
- **c:** star joins work in a metric view.
- **d:** a parameter and a scalar subquery work in a metric view's `WHERE`.
- **e:** the CLI generates and binds dashboards.

**Departures from the spec.**
- No `warehouse_id` variable: each re-export rewrites the resource file.
- The hospital table lists only hospitals with 11+ stays, rather than about
  150 rows that are mostly blank.
- Secondary suppression (E61).
- `shown()` and `kpi_window` live in `sql/dashboard_support.sql`, not in
  `metric_views.sql` (E60).
- Rare visit types fold into `other` (seven series; the dataviz rule caps a
  stacked chart at eight).
- Hidden cells read `null`, because AI/BI shows NULL that way, and the page
  says so.

**The text-to-SQL contestant, after the metrics layer grew.**

| Run | metrics | raw | What changed |
|---|---|---|---|
| dev-2 (baseline) | 16 | 12 | |
| dev-3 | 13 | 12 | it used `shown()` (E60) |
| dev-4 | 15 | 12 | `shown()` moved out |
| dev-5 | 16 | 12 | `METRICS_NOTE`: nothing follows GROUP BY ALL |

dev-5 fails exactly dev-2's four questions. The bar was "no repeatable new
failure", because `raw` flips about 3 of 20 verdicts between identical runs.
The phase 5 test runs used the earlier note and views.

**Limits.**
- **Some "hospitals" are outpatient clinics.** Synthea puts some inpatient
  encounters at clinics, and the largest row in the hospital table is one.
- **Every hospital row but the largest rests on 11-16 stays.** Their cost gaps to the network
  (one is 91% below) are too thin to act on one by one, and the summary
  says so.
- **The 30-day readmission rate (1.39% for 2020-2026) is far below
  real-world levels,** because the data is synthetic.
- **The executive summary is a dated snapshot.** Its window (Aug 2025 - Jul
  2026) and numbers were written by hand from this data load. The widget
  descriptions say only "last 12 complete months", which `kpi_window`
  computes.
- **The dashboard is dev only.** It reads `healthcare_dev`, and
  `include: resources/*.yml` would also add it to a prod deploy, which this
  project never runs.
- **The checks behind "none unnamed".** `check_metrics.sql` counts an empty
  hospital name as unnamed. A missing organization gives `''` under
  `concat_ws`, not NULL. Stay costs are checked against `fact_encounter`
  (each hospital encounter's cost lands in exactly one stay).

### D75 — phase 9: retraining on drift, replayed through Airflow

**Why.** D71 left a drift report saying the 2020-2026 patients are not the
ones the model learned from, and a champion whose cutoff was set to flag
about 22% of stays, as the rule does, but flags 31-36% of production stays.
D73 left a rule: no training on a table no gate has checked. Phase 9 builds
the loop that acts on drift, and Airflow's part in it.

**The data never changes, so a date cursor stands in for time.** Both
Synthea batches cover one fixed calendar. A DAG that runs drift and then
retrains would fire once and never meaningfully again. Instead, each run is
told "today is `as_of`" and sees only what was known then. Six yearly
cursors, 1 January 2021 to 1 January 2026, replay the policy in a sandbox.
One live run then applies it for real.

**The rule at one cursor** (`scripts/retrain.py`, tested on made-up rows):
- **Windows** (by admit day): the check window is the 12 months before
  `as_of`, and the cutoff window the 12 before that. A label counts only if
  the discharge was 30 or more days before `as_of`.
- **Budget:** the rule's flag rate on phase 6's training stays, 21.8%.
  Computed, never typed, and the same for every cursor.
- **Trigger:** the champion's flag rate on the check window, with its 95%
  Wilson interval. It triggers when the interval excludes the budget.
  Feature drift is computed every time, but only explains a trigger.
- **Two challengers:**
  - a **new cutoff**, the same model with its cutoff re-set to flag 21.8%
    of the cutoff window;
  - a **retrain**, the champion's own kind and settings refitted on every
    labelled stay before the check window.

  Scores on stays a model trained on are out of fold (D72).
- **The gate**, on the check window, which neither challenger saw:
  - **workload:** the challenger's flag-rate interval contains the budget;
  - **a ranking guard:** the challenger is not clearly worse at ranking
    than the champion (average precision, patients resampled 1,000 times;
    it fails only if the whole interval is below zero).
- **Winner:** the new cutoff if it passes, then the retrain, else nothing.
  The smaller change wins.
- **Why workload and not accuracy:** about 5 readmissions a year. No
  one-year window can show that one model ranks better than another (phase
  6 fixed 30 as the bar), so the guard catches gross failure only. The
  claim phase 9 can make is "retraining keeps the review workload at the
  budget", not "retraining improves accuracy".

**The pieces.**
- **`notebooks/retrain_readmission.py`** runs one cursor (`as_of`, `mode`).
  It appends one row to `ml.retrain_history`, logs an MLflow run, and on a
  win registers a version with its cutoff and training dates as tags:
  - a new cutoff is `copy_model_version`;
  - a retrain is a newly logged model.

  It moves `replay_<year>` in replay mode, or `champion` in live mode.
  - **An order guard runs before any compute.** Replays go one year at a
    time from 2021, a live run needs all six, and nothing repeats.
  - **The history row is written last,** so a crash leaves a spare version,
    never a decision without a record.
- **`orchestration/dags/retrain.py`** (`schedule=None`,
  `max_active_runs=1`, `retries=0`, typed `as_of` and `mode` params) runs
  four tasks:
  - `gold_is_gated` fails unless no pipeline update is running and the
    latest real one COMPLETED;
  - `retrain` submits the notebook;
  - `promoted_live` reads its exit value and logs it;
  - `rescore` runs `score_readmission` after a live promotion only.

  The notebook does all the compute in one serverless job; splitting it
  into tasks would cost a cold start each.
- **`score_readmission` changed by one line:** it scores from the
  champion's `train_admit_before` tag when it is later than 2020
  (`rt.scored_from`), so a retrained champion never scores its own training
  stays. On v2 it moved nothing (the fingerprint matched).
- **`rm.patient_resamples`** was pulled out of `bootstrap_difference` for
  the ranking guard. A test pins every draw to the old loop, so D71's
  intervals stand.

**Probes** (`notebooks/probe_retrain.py`, the provider's hook in the
container, and a throwaway DAG):
- **P1:** `copy_model_version` works on Free Edition. The copy keeps the
  source's run id and tags, and scores identically.
- **P2/P3:** the hook's endpoints take no `api/` prefix (`2.0/pipelines/...`,
  `2.1/jobs/...`). Updates come newest first, with `validate_only` on each.
- **P4:** a typed `Param(format="date")` is enforced at trigger time on a
  `schedule=None` DAG. A bad date or no date creates no run.
- **P5:** v2's flag rate by year matches D71 (2020-2025: 31.4-35.7%).
- **P6:** the last admit day in `readmission_signals` is 2026-07-14, so the
  live run's `as_of` is 2026-07-15.
- **P7:** v2's kind and settings come back from its run's params.

**The six years** (budget 21.8%):

| Cursor (checks) | Champion | Flag rate (95%) | Triggered | New cutoff | Retrain | Outcome |
|---|---|---|---|---|---|---|
| 2021 (2020) | v2 | 31.6% (27.4-36.1) | yes | 23.0% pass | 23.7% pass | **new cutoff → v4** |
| 2022 (2021) | v4 | 21.2% (17.6-25.2) | no | | | no trigger |
| 2023 (2022) | v4 | 23.3% (19.1-28.2) | no | | | no trigger |
| 2024 (2023) | v4 | 25.2% (20.9-30.1) | no | | | no trigger |
| 2025 (2024) | v4 | 26.1% (21.8-30.9) | no | | | no trigger |
| 2026 (2025) | v4 | 27.7% (23.3-32.6) | yes | 26.6% fail | 29.4% fail | **none passed** |

The ranking guard read "not worse" both times it ran. In every row, the
features with status "shifted" include conditions at admission,
hypertension, heart disease or stroke and, from 2023, age.

**What the replay found.**
- **The drift began before 2020.** The spec predicted both challengers
  would fail at 2021, because their cutoff comes from 2019, which "did not
  know 2020 was coming". Instead the 2019 cutoff (0.0118, against v2's
  0.0078 set on all of 2010-2019) flagged 23.0% of 2020. Scores were
  already higher in 2019 than across the training decade, so 2020
  continued a trend rather than breaking it. This answers the question D71
  left open ("per-year training rates were not computed").
- **After one promotion, a slow creep.** v4's rate rose about 1.5 points a
  year, from 21.2% to 27.7%.
- **The trigger cannot see a slow trend.** At 330-450 stays a year the
  interval is about ±4.5 points, so the creep stayed "on budget" for four
  years. 2025's lower bound sat exactly on 21.8%.
- **When it fired again, neither fix worked.** A cutoff learned from last
  year is one year behind, and from 2024 to 2025 the scores moved more than
  the interval's width. The gate judged correctly; the weakness is the
  policy.
- **Retraining never beat moving the cutoff** (23.7% against 23.0%, and
  29.4% against 26.6%). On this data a new model added nothing a new
  threshold did not.

**The live run** (`as_of` 2026-07-15, starting from live v2):
- **Before it, the sandbox check passed.** Both `ml` fingerprints were
  identical to the before-record, and `champion` was v2 in both models.
- **The run:** v2 flagged 33.5% (28.9-38.5%) of mid-2025 to mid-2026. The
  new cutoff, set on mid-2024 to mid-2025, flagged 20.3% and passed; the
  retrain flagged 23.0% and also passed.
- **So `champion` moved to v5:**
  - v5 is v2's model with cutoff 0.0201;
  - `rescore` added v5's 2,451 rows to `ml.readmission_scores` (11,769 in
    all, beside v1's and v2's);
  - `ml.drift_report` did not change, and `no_bypass` stays at v2;
  - the snapshot was not rerun, because it reads only `model_results` and
    `drift_report`.
- **Read with care.** The 2026 replay failed and the live run passed, and
  their windows are only six months apart. A cutoff is the 78th percentile
  of about 350 scores, so it is itself noisy, and moving the window by half
  a year moved the verdict across the line.

**The loop's limits, said plainly.**
- Every decision rests on about 350 stays.
- The trigger sees moves of about 5 points, not trends.
- The cutoff lags by the length of its window.

Each decision is honest about what it measured; none is precise.

**Decisions made while planning or building.**
- **P-a:** the probes found the endpoints without the `api/` prefix, so the
  DAG uses `2.0` and `2.1`.
- **The snapshot is not rerun** after a live promotion: it reads nothing
  that changes (against spec §8 step 9).
- **The live run decides from live v2.** The replay's promotions do not
  carry into it (spec §2.7).
- **The 2021 cursor ran by hand first** (`run_notebook.sh` now takes JSON
  parameters), to time it before the backfill. Each cursor takes about two
  minutes.
- **Errors:** E63 (E32's timeout, on a stack long up) and E64 (a pasted
  heredoc garbled).

**What phase 10 receives.**
- A champion (v5) chosen by a rule that was replayed before it was trusted,
  and `ml.retrain_history`: seven decisions with their rates and reasons.
- Two named weaknesses, neither built:
  - a cutoff set on recent months rather than a whole year (the lag);
  - a trend test across cursors (the trigger's blindness).
- A DAG pattern that any further model can follow: a gate first, one
  compute job, a branch on its outcome, then downstream.

### D76 — the public app redesigned: a pipeline map and research-paper chapters

**Why.** The Streamlit app was five stock pages: titles, `st.metric` tiles,
default bar charts and grey captions under each. It looked like every other
Streamlit app, ended at phase 6, and still showed phase 2's numbers on its
home page. A recruiter scanning it saw a generic dashboard, not a lakehouse.

**The idea, chosen from three directions mocked up with real numbers** (a
research paper, a clinical lab report, a pipeline map):
- **The home page is the architecture.** A transit-style map from Synthea
  through bronze, silver and gold to the story, the model and the retraining
  loop. Each station is a chapter, carries the one number that chapter
  answers (computed from the snapshots), and opens it.
- **The chapters read like a research paper.** A kicker, a title and a
  standfirst; key numbers in a monospace face; numbered figures; verdicts as
  stamps; and every caveat and decision number as a numbered margin note
  instead of a grey caption. Tables move into "Method" expanders, so the
  reading column holds prose, numbers and figures.
- **"Layer metals".** Bronze, silver and gold are the map's lines and the
  pages' accents, on paper (light) or the map's night canvas (dark); the app
  follows the viewer's setting. Fraunces for titles, Source Serif 4 for text,
  JetBrains Mono for numbers, Inter for labels.

**What changed.**
- **Six chapters, not five:** chapter 6, "The model keeps its promise", is
  phase 9's retraining loop (D75): the seven runs, each champion's flag rate
  with its interval against the budget, and both challengers.
- **A new snapshot, `retrain_history.parquet`,** from `ml.retrain_history`.
  `publish_retrain_history` refuses anything that is not a rate, a known
  label or a feature name, and any window or flagged count of 1-10. Five
  new tests.
- **Chapter 5 shows the verdict's own evidence:** the model-minus-rule
  difference with its 95% interval against zero, for both populations. A
  recall chart would have shown only the base rate: every model and rule
  recall rests on 1-10 readmissions caught or missed and is hidden (D66).
- **Chapter 4's signals are small multiples on one shared axis,** with each
  level's 95% interval and the overall rate dashed. The old page gave every
  signal its own axis, so they could not be compared.
- **The numbers are live, not typed.** The old home page said 104
  quarantined rows of 3.28 million: phase 2's batch alone. With D65's second
  batch it is 1,023 of 36.3 million, and the map now reads it from the
  snapshot.
- **The model's live champion is v5** (chapter 5's margin), not v2.

**How it is built.**
- `app/streamlit_app.py` is a router: `st.navigation(position="top")` over
  `app/chapters/` (home, then c1-c6).
- `app/ui.py` is the design kit: `chapter()`, `section()` (a reading
  column and its margin, which drops below on a phone), `numbers()`,
  `stamp()`, `notes()`, `figure()` (an Altair chart in the app's theme plus
  its numbered caption), `strip()` (the map as a "you are here" line),
  `pager()` and `colophon()`. `app/style.css` is the one stylesheet; it names
  no colour, and `ui.style()` prepends the palette for the viewer's mode
  (`st.context.theme`).
- `.streamlit/config.toml` sets both modes (`[theme.light]`, `[theme.dark]`)
  and the Google fonts. Streamlit is upgraded from 1.39.0 to 1.65.0, and
  Altair 5.5.0 is pinned, in both requirement files.
- **The chart palette was validated, not eyeballed:** the dataviz validator
  passed bronze `#9A5A12` and steel `#3A68A8` on paper, gold `#B8861A` and
  steel `#5B8FDB` on the dark canvas (lightness band, chroma, colour-blind
  and normal-vision separation, contrast). Grey neutrals and a teal failed
  first. Every two-series chart also carries direct labels or shapes.

**Things found while building.**
- `st.html`'s sanitiser drops SVG entirely; the map renders through
  `st.markdown(..., unsafe_allow_html=True)`, links included.
- Streamlit reruns a changed page script but keeps an imported module
  (`ui.py`) cached until the server restarts.
- Vega-Lite point charts include zero by default, which squashed chapter
  6's 20-35% band into the top of the chart; their scales are now explicit.

**Not done.** No page for the gates (phase 7: nothing aggregate to
publish) or the operations dashboard (phase 8: behind the workspace login).
`pyyaml` stays in `app/requirements.txt` though the app no longer imports it.

### D77 — the operations dashboard joins the app, and a spacing pass

**Why.** Phase 8's dashboard (D74) is the most analyst-facing piece of the
project, and the public app left it out: it sits behind the workspace login,
so a reader saw only a README screenshot. Showing it is what a pitch needs.

**What changed.**
- **Chapter 07, "Running the network",** a spur off Gold on the map. Five
  tiles against the prior twelve months, three findings and three
  recommendations, visits by type month by month, length of stay and cost
  by quarter, and the payer and hospital tables. It is wider than the paper
  chapters (1320px), because tables and charts need the room.
- **Its numbers are the dashboard's own SQL.** `publish_snapshot.ops_queries`
  reads each dataset from `dashboards/operations.lvdash.json` and runs it with
  every filter at "All". The app cannot disagree with the dashboard's
  default view, and `shown()` and the payer table's secondary suppression
  (E61) run in one place. Five new snapshots: `ops_kpi`, `ops_visits`,
  `ops_stays`, `ops_payers`, `ops_hospitals`.
- **Hospital and insurer names are replaced before saving.** Synthea takes
  them from real Massachusetts hospitals and real insurers; synthetic costs
  beside a real name read as a claim about it. Hospitals become "Hospital A,
  B, …" by stays, commercial insurers "Commercial payer 1, 2, …"; Medicare,
  Medicaid, Dual Eligible and No insurance keep theirs (programmes, not
  companies). `check_only_categories` refuses any other name.
- **What the publish refuses** (`publish_ops`, seven tests): a shown count of
  1-10; any hidden visit or stay cell in the trends, which the twelve-month
  tiles would give back by subtraction; exactly one hidden payer, or hidden
  payers or left-out hospitals adding up to 1-10 against the stays tile.
- **The findings are written by the page** from the snapshot, so a new
  publish rewrites them; a finding whose number is hidden is left out.
- **Left out of the dashboard:** the "share of network" tile (always 100
  with no filter), the network-gap table (all zeros with no filter), the
  care-gap table (chapter 3 has it), and the filters. Filtering a public
  page means publishing every combination and proving no two of them give a
  hidden count back; the live dashboard is safe because each query is
  suppressed on the group the viewer picked.
- **Visits by type are one small chart per type,** sharing the month axis,
  each on its own scale. The dashboard stacks seven types in seven colours;
  the app has two validated chart colours.

**The spacing pass** (ui-ux-pro-max's checks, then each page at desktop and
phone width):
- the ten stock `st.dataframe` grids became `ui.table()`: rules, not a grid,
  numbers right-aligned in the mono face, an empty cell named (`hidden` on
  chapter 7);
- key numbers are a grid that shares out the row, with an optional
  comparison line under each;
- margin notes are set smaller and tighter; `ui.notes(across=True)` lays them
  side by side under a full-width block;
- the "you are here" strip renders at last (E65), and the small-multiple
  charts no longer clip on a phone (E66, E67);
- the footer's GitHub link opens a new tab (GitHub refuses to load inside
  streamlit.app's frame), and the map's ignored `url_path="map"` is gone.

**The README screenshot.** The old one showed the real hospital and insurer
names, so a reader could match "Hospital A" to a real name by its numbers.
It is replaced by a capture of chapter 7 (`docs/img/operations-chapter.png`).
The old image stays in git history; rewriting history for it was not worth
breaking every clone. A "hidden" cell is now right-aligned like the numbers
it stands in for, which the capture showed it was not.

### D78 — phase 10: CI becomes a gate

**Why.**
- CI was an alarm, not a gate (E33's own words): every phase was merged
  locally and pushed to `main`, so checks reported after the code had
  landed. `main` is what the public Streamlit app deploys.
- The Airflow DAGs were never loaded in CI. ruff lints them as Python; a
  wrong Airflow import or a DAG that stops parsing passed green.
- Nothing checked that the app's pins match the project's (the note after
  D26: "not enforced today").
- One test flaked: a 5 s clock limit on work that takes 1.8 s on a quiet
  laptop and crosses 5 s under load. A flaky test in a blocking gate blocks
  merges on noise.

**The gate** (set with `gh api`, read back 2026-10-07):
`{"admins":true,"checks":["lint","bundle","dags"],"delete":false,"force":false,"linear":true,"reviews":0,"strict":true}`.
- `enforce_admins`: the only person who pushes is an admin, so without it
  the gate would be optional for the one person it applies to.
- 0 approvals: GitHub does not let an author approve their own pull request.
- Squash merge only, head branches deleted on merge. A phase merges as
  `git push -u origin phase-N`, `gh pr create --fill`,
  `gh pr merge --squash`; one commit per phase, as before.

**The third job, `dags`.** It builds `orchestration/Dockerfile`, the image
the laptop runs, and parses `dags/` inside it with
`orchestration/ci_check_dags.py`: no import errors, and the DAG ids exactly
`{medallion, retrain}`, so a DAG that silently stops loading and a new one
nobody added to the check both fail. The script sits beside `dags/`, not in
it, because Airflow parses every file in `dags/`.

**The two tests.**
- `tests/test_requirements_agree.py`: every pin in `app/requirements.txt`
  must be the root's pin. It found one gap on day one, an unpinned
  `pyarrow` in the root file, now `pyarrow==16.1.0`.
- The timing test became a growth test: 1,000 rows against 10,000, failing
  above 30x. Linear work is about 10x (measured 8.6x and 8.2x), quadratic
  about 100x (a stand-in measured 116x). Load slows both runs alike, so the
  ratio holds where a clock limit did not.

**Probes.**
1. `DagBag` lives in `airflow.dag_processing.dagbag` in Airflow 3.3.2 and no
   longer takes `include_examples` (E68). No metadata database is needed.
2. `dags` takes 56 s on a GitHub runner, cold. No layer caching.
3. `gh api` set branch protection with this login; no Settings clicks.
4. `pip install -r requirements.txt` resolves with `pyarrow==16.1.0`
   (`lint` green).

**Proof, 2026-10-07.**
- Phase 10's own pull request (#4): all three green before protection was
  switched on, because GitHub can require only a check it has seen run.
- Pull request #5 appended `import no_such_module  # noqa: E402,F401` to
  `retrain.py`: `lint` and `bundle` passed, `dags` failed, and GitHub read
  the pull request as `mergeStateStatus: BLOCKED`. The merge attempt itself
  was stopped by the assistant's own safety check before it reached GitHub,
  so the evidence is GitHub's merge state, not a refused merge command.
  Closed unmerged, branch deleted.
- An empty commit pushed straight to `main`: `GH006: Protected branch update
  failed`, exit 1. Dropped locally.

**Not done, and why.**
- Continuous deployment (`bundle deploy -t dev` on merge): a separate
  decision, which now has a trustworthy `main` to build on.
- `--validate-only` in CI: it spends serverless quota on every pull request.
- Type checking or SQL linting: no failure in this project's history asks
  for them.
- A service principal or OIDC: the personal token stays the Free Edition
  degradation, now used by `bundle` on every pull request.

**Emergency.** Turn `enforce_admins` off in Settings, merge, turn it back
on. Each use is an errors.md entry.

### D79 — the audit: three findings fixed, one platform limit found

**Why.** After phase 10 an independent reviewer, given the code but not this
log, challenged every decision (2026-10-07). Thirty-two challenges; argued
against this log, most were answered or narrowed. Three were defects a
reader of the repo could find alone, and these are fixed here.

**1. Two unmasked copies of the patient table.**
- `silver.v_patient`, the typed view `silver.patient` is built from, was a
  *published* materialized view: SSN, names, address, coordinates and birth
  dates, untagged, beside the masked table. `bronze.br_patients` held the
  same identifiers as raw strings, also untagged. patient.sql said "all
  identifying columns live here and nowhere else". An uncleared read
  returned real values from both. On a one-account workspace nobody could
  exploit it (D49); the claim was still false.
- `v_patient` is now a `TEMPORARY VIEW`: computed inside the update,
  stored nowhere. **PRIVATE was tried first and is not enough.** The
  pipeline stores a private view anyway, renamed
  `bronze.__<pipeline id>_v_patient`, with its own backing table.
- Removing a view from the pipeline does not drop it. The stale
  `silver.v_patient`, the private copy and their two backing tables were
  dropped by hand.
- `sql/governance_bronze.sql` tags br_patients' 19 identifier columns with
  the silver values. Every bronze column is a string, so one bronze policy
  covering all eight values masks to `'***'`; it replaces the five-value
  policy from governance_notes.sql. A selective refresh of `silver.patient`
  then read 12,580 patients, none masked, no blank birth dates: the
  pipeline still reads bronze as a cleared user.
- **CHECK 3** in governance_check.sql lists every column named like one of
  the identifiers, in any schema, that carries no tag. CHECKs 1 and 2 only
  see columns someone tagged. It was seen failing on the real catalog first
  (v_patient and br_patients, 19 columns each), then passing.

**The limit it found.** Every pipeline table keeps its rows in a MANAGED
`__materialization_mat_<pipeline>_<name>_<n>` table in the same schema. Read
by an uncleared owner, silver.patient's returns every row with real SSNs:
past the masks and past the row filter. Tagging it is permitted, and was
tried: it still returned real values, while br_patients, tagged the same
minute, was masked. Schema policies do not reach backing tables. The tags
were removed again, so no tag claims a mask that does not apply, and CHECK 3
skips backing tables with that reason written beside it. Another principal
would be granted the table, not its backing table; here the owner reads
everything (D49). The README's degradation row says so.

**2. The story published a 10 by subtraction.** Four admit reasons were
hidden, and 140 − 71 ("other") − 59 (bypass history) = 10 readmissions
among them; the colophon says any group of 1-10 is hidden "with whatever
would give it back by subtraction". D66's rule handled exactly one hidden
level. Now a signal hides more levels until the hidden ones hold 0 or 11+
stays and readmissions between them (`complete_suppression`), and
`check_small_cells` refuses to publish otherwise. The extra level is the
catch-all "other" first, as the level that means least; the rule's old
choice, the smallest, would have hidden the bypass level chapter 4 quotes.
Only that row of `story_levels` changed. A count of 10 is already in git
history; on synthetic data, rewriting history for it is not worth it.

**3. The prod target was a claim.** CI validated `-t prod`; it was never
deployed (a fixed rule), and the notebooks, SQL and dashboard all name
`healthcare_dev`. Dropped from databricks.yml, CI and the catalog setup.
The empty `healthcare` catalog still exists in the workspace; nothing
reads it.

**Error.** E69: `governance_verify.sql` restored clearance with two values
after the row filter made it three columns. A probe copied it and left the
only account uncleared for under a minute. Fixed in both.

**Not done** (the reviewer's other findings, for a later choice): the
training window starts in 1915 and the model's verdict is judged at a
cutoff it does not deploy at; the snapshot guards are per path rather than
one deny-by-default role map; `setup-cli@main` is unpinned and no test
parses the SQL; the clearance check D47 asks for before a gold build is
not a task in the medallion DAG.

### D80 — the model, re-judged: trained from 2000, compared where it runs

**Why.** The audit after phase 10 (D79) found two things wrong with phase
6's verdict, and the code agreed with it.
- **Training reached back to 1915.** `split()` had an upper bound only.
  Production patients (2020-2026) were older and sicker than a century of
  training stays, so drift was there on day one: age PSI 0.35, and the
  2020 flag rate 32% against a 21.8% budget. D71 said per-year training
  rates were never computed; D75's "drift began before 2020" was partly
  this.
- **The verdict was judged where nothing runs.** "No better" compared model
  and rule at the rule's own alert count, 35.4% of production stays. The
  model is deployed at a cutoff set to flag the rule's *training* rate.
  The rule is yes/no, so it cannot move to that budget, which is why it
  was compared at its own count. The fair baseline at the deployed budget
  is the rule with a random share of its alerts dropped: its expected
  recall is its own times the share kept (`thinned_rule_recall`).

**The probe** (`notebooks/probe_window.py`, read-only: nothing logged or
registered). Every window, "all" population; production 2,451 stays, 34
readmissions; model minus rule in points of recall, 95% interval:

| Training from | Stays / readmissions | Age PSI | Budget → production flag rate | At the rule's count | At the deployed cutoff |
|---|---|---|---|---|---|
| 1915 (phase 6) | 8,240 / 104 | 0.35 | 21.8% → 32.9% | -3.0 to +29.0 | +2.4 to +32.8 |
| **2000** | 5,180 / 71 | 0.18 | 24.9% → 31.9% | +5.5 to +36.0 | +14.1 to +41.8 |
| 2005 | 4,121 / 62 | 0.13 | 26.3% → 32.4% | +3.6 to +27.5 | +3.0 to +28.3 |
| 2010 | 2,859 / 41 | 0.07 | 28.6% → 31.4% | 0.0 to +28.6 | +5.5 to +34.5 |

**The choice, and how it was made.** The verdicts were seen before the
window was chosen, so the window is not chosen by them. The rule: the
longest window whose age and condition PSI against production are both
below 0.25 ("shifted"). That is 2000. Each window's verdict at the deployed
cutoff is "beats", the 1915 one included, so the change of verdict does not
rest on the choice. Cross-validated average precision falls as the window
shortens (0.142, 0.123, 0.109, 0.087): less history, fewer readmissions to
learn from.

**What changed.**
- `rm.TRAIN_FROM = "2000-01-01"`, the default of `split()`, so training,
  scoring, drift and phase 9's budget all use it.
- `evaluate()` also judges at the deployed cutoff: `cut_low/mid/high` and
  `cutoff_verdict` in `ml.model_results`, beside D71's `diff_*` and
  `model_verdict`. Versions carry `beats_rule_at_cutoff` and
  `train_admit_from` tags.
- Retraining fits on the 20 years before each run (`rt.TRAIN_YEARS`,
  `trained_on(..., admit_from)`), so no cursor trains on 1915 again.
- Chapter 5 headlines the deployed comparison and shows both; chapter 6's
  findings are rewritten from the new replay.

**Results.**
- Phase 6: "all" champion v6, logistic regression (C = 1), cut-off 0.00642;
  **beats** at the deployed cutoff (+27.4, +14.1 to +41.8) and at the
  rule's count (+20.5, +5.5 to +36.0). "No bypass" v3, gradient boosting:
  too few to judge (17 readmissions). Brier equals the base rate's;
  average precision is four times it.
- Drift: age and conditions "watch" (PSI 0.18, 0.19), no longer
  "shifted". The yes/no conditions and admit reason still are.
- Phase 9, rerun: `ml.retrain_history` was renamed
  `ml.retrain_history_d75` and the stale `replay_2021` alias removed, so
  the order guard allowed a clean replay. Budget 24.9%.

| Cursor (checks) | Champion | Flag rate (95%) | New cutoff | Retrain | Outcome |
|---|---|---|---|---|---|
| 2021 (2020) | v6 | 35.9% (31.6-40.6) | 31.3% fail | 31.3% fail | none passed |
| 2022 (2021) | v6 | 28.2% (24.2-32.5) | | | no trigger |
| 2023 (2022) | v6 | 29.4% (24.7-34.5) | | | no trigger |
| 2024 (2023) | v6 | 29.9% (25.3-35.0) | 24.3% pass | 23.5% pass | new cutoff → v7 |
| 2025 (2024) | v7 | 29.2% (24.7-34.1) | | | no trigger |
| 2026 (2025) | v7 | 30.5% (25.9-35.5) | 28.0% pass | 27.7% pass | new cutoff → v8 |
| live, 2026-07-15 | v6 | 35.7% (31.0-40.7) | 25.7% pass | 23.5% pass | new cutoff → **v9, live** |

  The replays and the live run were submitted with `run_notebook.sh`, not
  through the Airflow DAG: the same notebook, without the DAG's gate task.
  The pipeline's last update had completed. Rescored with v9 afterwards.

**What the rerun overturned in D75.** D75 found 2020 continued a trend (a
2019 cutoff fitted it). On the 2000-2019 model, 2020 is a break: neither
challenger could bring it back to budget. D75's version was an artefact of
the century-long window. Still true: a retrained model never caught what a
new cutoff missed. New: each fix lasts about two years before the trigger
fires again.

**Not done.** The reviewer's remaining findings stay as D79 lists them. The
thinned rule is a weak baseline on purpose (the same rule, fewer alerts);
a rule that ranks its own alerts, by age say, would be a stronger one.
