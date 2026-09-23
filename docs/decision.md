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
