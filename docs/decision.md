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
