# Error log

Every error hit while building this, with the symptom verbatim, the actual
cause, and the fix. Append as they happen.

**Why keep this separately from `decision.md`.** The two are indexed
differently, which is the whole point:

- **This file is keyed by symptom** — the message you actually saw. You come
  here when something breaks and you want to know whether it has broken before.
- **`decision.md` is keyed by choice** — what we picked and why.

An error that forced a design choice appears in both, cross-linked. E4 and D9
are the same event described for two different readers.

**Silent wrongness counts as an error here.** Several of the worst entries below
never produced a stack trace — the code ran, the numbers came out, and only the
meaning was destroyed. Those are the ones worth rereading.

---

## Symptom index

| # | What you see | Task |
|---|---|---|
| [E1](#e1) | `ResolutionImpossible` from pip | 1 |
| [E2](#e2) | `UnsupportedClassVersionError … class file version 61.0` | 2 |
| [E3](#e3) | Generated names look like `Abdul218` | 2 |
| [E4](#e4) | `ParserException: syntax error at or near "$2"` | 3 |
| [E5](#e5) | `UnicodeEncodeError` on DuckDB table output | 3 |
| [E6](#e6) | Plan said 1,000 patients, `patients.csv` has 1,148 | 3 |
| [E7](#e7) | Report full of zeros, exit code 0 | 3 |
| [E8](#e8) | Tests green, totals still wrong | 3 |
| [E9](#e9) | `E501 Line too long` | 3 |
| [E10](#e10) | `databricks bundle` does not exist | 5 |
| [E11](#e11) | `'databricks' is not recognized as the name of a cmdlet` | 5 |
| [E12](#e12) | `bash: .venv/bin/activate: No such file or directory` | 6 |
| [E13](#e13) | `Error: no such directory: /Volumes/…/csv` | 6 |
| [E14](#e14) | Upload prints errors, then prints `Done.` | 6 |
| [E15](#e15) | One entity silently absent from the upload | 6 |
| [E16](#e16) | Commit lands with a failing lint gate | 6 |
| [E17](#e17) | `Data source cloudFile is not supported ... on a shared cluster` | 7 |
| [E18](#e18) | `Input path ... /patients.csv is not a directory` | 7 |
| [E19](#e19) | `An active update ... already exists for pipeline` | 7 |
| [E20](#e20) | A scratch script leaves the repo modified | 7 |
| [E21](#e21) | `KeyError: 'DATABRICKS_HOST'` although `.env` exists | 8 |

---

## Task 1 — scaffolding

### E1 — pip cannot resolve pyarrow {#e1}

```
ERROR: ResolutionImpossible
```

**Cause.** `requirements.txt` pinned `pyarrow==17.0.0`, but
`databricks-sql-connector==3.4.0` constrains pyarrow to an older range. Two hard
pins, no overlap.

**Fix.** Remove the pyarrow pin entirely. It exists only so pandas can read and
write Parquet, and the connector already bounds it. Resolved to 16.1.0.

**Lesson.** Do not pin a transitive dependency you have no opinion about. The
pin is now accompanied by a comment saying why it is absent, so nobody helpfully
adds it back. → [D3](decision.md)

---

## Task 2 — Synthea generation

### E2 — Synthea will not start on Java 15 {#e2}

```
UnsupportedClassVersionError: ... has been compiled by a more recent
version of the Java Runtime (class file version 61.0)
```

**Cause.** Class file version 61 means Java 17. The machine had JDK 15.

**Fix.** `winget install EclipseAdoptium.Temurin.21.JDK`. Installed alongside
JDK 15 rather than replacing it, so `java` on PATH may still resolve to the old
one — the documented command calls the Temurin binary by absolute path.

**Lesson.** Caught by a 3-patient smoke test, not by a 10-minute full run. That
smoke test is now a documented step in `synthea/README.md`. → [D7](decision.md),
[D8](decision.md)

### E3 — names generate as `Abdul218` {#e3}

**No error message. Nothing failed.** Found by opening an actual smoke-test note
and reading it.

**Cause.** `generate.append_numbers_to_person_names` defaults to `true`.

**Why it is the worst entry in this file.** Phase 3's de-identification
benchmark is the project's AI centerpiece and its headline number is
name-detection F1. With trailing digits left on, the regex `[A-Za-z]+\d+` scores
near-perfectly, and the entire staged baseline-to-model comparison measures
nothing. Every number would still have been produced. Only the meaning would
have been gone.

**Fix.** `generate.append_numbers_to_person_names = false`, re-verified with a
3-patient run (`Benjamin Littel`, `Juliette Streich`).

**Lesson.** Read the actual output, not just the config. Recorded in four places
because it fails silently: `synthea.properties`, `synthea/README.md`,
`CLAUDE.md`, spec §4.3. → [D5](decision.md)

---

## Task 3 — calibration

### E4 — DuckDB rejects a bound parameter in `COPY … TO` {#e4}

```
duckdb.duckdb.ParserException: Parser Error: syntax error at or near "$2"
```

**Cause.** `COPY (...) TO $2 (FORMAT PARQUET)`. DuckDB's `COPY … TO` target is a
**filename literal, not an expression**, so it cannot be a bound parameter. `$1`
in the same statement works because it sits inside `read_csv_auto(...)`, which
is expression position.

**Fix.** Drop the SQL. `con.read_csv(str(path), header=True).write_parquet(str(out))`
takes the output path as a Python argument, so there is nothing to interpolate
or escape.

**Note.** This was a bug in the *plan*, not in hand-typed code. → [D9](decision.md)

### E5 — console encoding blows up on DuckDB output {#e5}

```
UnicodeEncodeError: 'charmap' codec can't encode character ...
```

**Cause.** Windows console defaults to cp1252; DuckDB prints results in a
box-drawing table.

**Fix.** `PYTHONIOENCODING=utf-8` in front of the command.

**Related.** PowerShell also mangled a `python -c` invocation containing
embedded SQL quotes. Both were sidestepped by running those one-offs through
Bash instead. For anything longer than a line, write a file.

### E6 — patient count is 1,148, not 1,000 {#e6}

**Cause.** A wrong expectation in the plan, not a bug in anything. `-p 1000`
requests 1,000 **living** patients; Synthea generates deceased ones in addition.
Actual: 1,148 = 1,000 alive + 148 dead.

**Fix.** Correct the expectation, and invert the check — **exactly 1,000 would
be the bug**, because it would mean `generate.only_alive_patients` got flipped
on, biasing every downstream mortality and readmission figure.

**Lesson.** A check that fires on the wrong condition is worse than no check.

### E7 — a wrong `--output-dir` writes a zeroed report and exits 0 {#e7}

```
skipping patients.csv — not found
... (12 lines)
wrote docs\calibration.md
```

**No error. Exit code 0.** The report is structurally valid and full of zeros,
written over the committed one.

**Cause.** `main()` skipped missing files and never checked whether anything had
been measured.

**Fix.** `if not rows: raise SystemExit(...)` after the loop. Same guard added to
`readmission_gate.py`, keyed on `inpatient_encounters == 0`.

**How it was found.** A review subagent ran the failure case instead of
reasoning about it.

**Lesson.** These reports are decision records that later phases extrapolate
from. A plausible wrong answer is worse than a crash, because a crash gets
fixed. → [D12](decision.md)

### E8 — the test suite passes while the totals are wrong {#e8}

**No symptom at all.** Found by mutation testing during review: deliberately
break the code, see whether any test notices.

**8 of 18 mutants survived.** The worst: swapping `**Total Parquet bytes:**` for
the CSV total — a 13× error in the exact number the report tells the reader to
size from — passed green.

**Fix.** One assert added to the existing test:
`assert "**Total Parquet bytes:** 256" in md`.

**Lesson.** "Tests pass" and "the code is right" are different claims. The
lesson generalised: `verdict()` in Task 4 was pure branching that produced the
project's go/no-go with zero coverage, and got tests for the same reason. →
[D14](decision.md)

### E9 — ruff fails on the plan's own code {#e9}

```
scripts\calibrate.py:54:101: E501 Line too long (112 > 100)
scripts\calibrate.py:86:101: E501 Line too long (102 > 100)
```

**Cause.** Both lines were copied verbatim from the plan. The plan's reference
code did not pass the project's own linter.

**Fix.** Wrapped. Also noted that `select = ["E","F","I","UP","B"]` omits `W`,
which is why trailing whitespace and a missing final newline passed silently.

---

## Task 5 — Databricks setup

### E10 — `databricks bundle` does not exist {#e10}

**Caught before it happened**, by checking the plan against what Task 7 needs.

**Cause.** The plan said `pip install databricks-cli`. That installs the
**legacy** Python CLI, which is deprecated and has **no `bundle` command at
all**. Task 7 and every later deployment run `databricks bundle deploy`, and the
spec's bundles-not-clicks decision is unimplementable without it.

**Fix.** `winget install Databricks.DatabricksCLI` — the modern CLI is a
standalone Go binary, versioned 1.x, not on PyPI.

**Why it would have been expensive.** The pip route appears to work at Task 5.
`databricks configure` and `current-user me` both succeed. It fails two tasks
later looking like a missing subcommand rather than a wrong install.

**Three similarly named things, one of which is a trap:**

| Name | What it is |
|---|---|
| `databricks-cli` (pip) | Legacy, deprecated, no `bundle` |
| `databricks` CLI | Go binary v1.x — the one you want |
| `databricks-sql-connector` (pip) | Python library for querying a warehouse |

→ [D17](decision.md)

### E11 — `databricks` not recognized, right after installing it {#e11}

```
databricks : The term 'databricks' is not recognized as the name of a
cmdlet, function, script file, or operable program.
```

**Cause.** Not a failed install — the binary was present and ran fine by
absolute path. Windows processes get a **copy** of the environment at start.
Winget wrote the new PATH to the registry; the already-running shell kept its
snapshot from before.

**Fix.** Open a new terminal. Or append in place, which preserves an activated
venv:

```powershell
$env:Path += ";$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Databricks.DatabricksCLI_Microsoft.Winget.Source_8wekyb3d8bbwe"
```

**Do not** rebuild `$env:Path` from the registry, which is the usual advice.
`Activate.ps1` prepends the venv to `$env:Path` in the current session only and
writes nothing to the registry, so a rebuild silently deactivates the venv and
`python` starts resolving to the system install.

**Also worth knowing.** `databricks --version` reporting `0.x` means the legacy
CLI is shadowing the new one on PATH.

---

## Task 6 — upload

### E12 — `.venv/bin/activate` does not exist {#e12}

```
bash: .venv/bin/activate: No such file or directory
```

**Cause.** `bin/` is the POSIX layout. On Windows the venv uses `Scripts/`, and
that holds in Git Bash too — the layout follows the platform the venv was
created on, not the shell reading it.

**Fix.** `source .venv/Scripts/activate`

**Worth internalising, because this recurs:**

| Command | Needs the venv? |
|---|---|
| `pytest`, `ruff`, `python -m scripts.*` | Yes |
| `databricks` anything, `upload.ps1` | No — system binary |

### E13 — `fs cp` fails on a directory that does not exist {#e13}

```
Uploading patients...
Error: no such directory: /Volumes/healthcare_dev/bronze/landing/csv
```

**Cause.** `databricks fs cp` does not create intermediate directories, and a
freshly created Unity Catalog volume is empty — `landing` existed, `landing/csv`
did not.

**Fix.** `databricks fs mkdir "$target"` before the loop, with its own exit
check. Verified idempotent: exit 0 on a second run, so it is safe unconditionally.

### E14 — the upload reports `Done.` after failing twelve times {#e14}

```
Uploading patients...
Error: no such directory: ...
Uploading encounters...
Error: no such directory: ...
...
Done.
```

**Cause.** `databricks fs cp` writes its error to stderr and PowerShell carries
on. Nothing checked `$LASTEXITCODE`.

**Fix.** `if ($LASTEXITCODE -ne 0) { throw "upload failed for $entity" }` after
each copy.

**Lesson.** Third time this shape has appeared — E7, E8, and now this. A script
that cannot fail is a script that lies. Any loop calling an external command
needs an exit check, or success is unfalsifiable.

### E15 — `immunizations` silently missing from the upload {#e15}

**No error.** Found by counting the entity list against `scripts/entities.py`:
11 versus 12. `immunizations` had dropped out between `procedures` and
`allergies`.

**Why it mattered.** Task 7 builds one bronze streaming table per entity from
`entities.py`. A missing file produces an empty table, and the debugging starts
in Auto Loader — two tasks downstream of the actual typo.

**Fix.** Restored, and both lists verified equal, same order. The duplication
between `upload.ps1`, `entities.py` and eventually `bronze.py` is deliberate
([D4](decision.md)) but only safe while someone keeps them in sync.

**Open.** That sync is currently trusted, not enforced. A test comparing the
lists is about six lines and belongs before `bronze.py` hardcodes the same
twelve a third time.

### E16 — a commit lands with `ruff` failing {#e16}

**Cause.** The verification command was
`pytest ... | tail -3 && ruff check . | tail -2 && git commit ...`. Piping
through `tail` replaces `ruff`'s exit code with `tail`'s, which is always 0. The
`&&` chain therefore continued past a failing gate and committed. `ruff` had
printed `Found 1 error` in plain sight and the chain ignored it.

**The underlying fault** was `scripts/run_sql.py:1 I001` — one missing blank
line before the first `def`. Trivial, auto-fixed with `ruff check --fix .`.

**The real error is the verification, not the lint.** This is the same shape as
[E7](#e7), [E8](#e8) and [E14](#e14): a check that cannot fail. Those three were
found in the project's own scripts. This one was in the command used to verify
the project's scripts, which is worse — a broken gate silently downgrades every
"tests pass, lint clean" claim made through it.

**Fix.** Let the checker's own exit code govern. Either run it bare:

```bash
ruff check .
```

or, if the output genuinely needs trimming, capture the status first rather than
piping it away. In a pipeline, `$?` belongs to the last command.

**Lesson.** Trimming output for readability is not free — it discards the exit
code, which is the part the `&&` was reading.

---

## Task 7 — bronze pipeline

### E17 — a typo that reports itself as a platform restriction {#e17}

```
[UNSUPPORTED_STREAMING_SOURCE_PERMISSION_ENFORCED] Data source cloudFile
is not supported as a streaming source on a shared cluster. SQLSTATE: 0A000
```

Repeated twelve times under roughly 2,000 lines of Scala stack trace.

**Cause.** `spark.readStream.format("cloudFile")` — singular. Auto Loader is
`cloudFiles`. Every option in the same block was correctly plural; only the
`format()` call was wrong.

**Why the message lies.** It is quoting the string back. Spark could not resolve
`cloudFile` to any registered source, then fell through to the shared-cluster
allowlist check — `DataStreamUtils$.validateAllowedSourceAndOptionsOnPE` in the
trace. `cloudFiles` is on that allowlist; `cloudFile` is on no list, because it
does not exist. So a security check fires before the friendly "no such data
source" error ever gets a chance.

**This cost about ten minutes of believing Free Edition had killed the bronze
design.** It had not. Auto Loader works fine on serverless.

**Fix.** `format("cloudFiles")`.

**Lesson.** When an error names a capability restriction, first check that the
thing being restricted is spelled the way you think. The plan had it right; this
one was hand-typing.

### E18 — Auto Loader handed a file instead of a directory {#e18}

```
CloudInvalidPathException: Input path s3://.../volumes/.../csv/patients.csv
is not a directory
```

**Cause.** `.load(f"{LANDING_PATH}/csv/{entity}.csv")`. Auto Loader watches a
**directory** for new arrivals and keeps a record of what it has already read.
A single file is not something it can stand guard over.

**Fix.** One directory per entity — `csv/patients/patients.csv` — and
`.load(f"{LANDING_PATH}/csv/{entity}/")`. Restructured server-side with
`databricks fs cp` between volume paths, so nothing was re-uploaded.

**Why not point all twelve at the shared `csv/` directory.** Every stream would
see every file, and all twelve tables would contain all twelve datasets. A
`pathGlobFilter` would prevent that, but each stream would still list all twelve
files on every poll, and the layout would have to be unlearned later. →
[D22](decision.md)

**Note.** A bug in the *plan*, not in hand-typed code — the fourth of those.

### E19 — `bundle run` refuses because an update is already active {#e19}

```
Error: An active update '60fb3dc0-...' already exists for pipeline '0a1b3a1c-...'
```

**Cause.** Not a second run of your own. A failed Lakeflow pipeline **retries
itself**; `databricks pipelines get-update` showed `cause: RETRY_ON_FAILURE`. A
pipeline permits only one active update, so the retry blocks a manual run.

**Fix.** Nothing. The retry started after the redeploy, so it was already
running the fixed code — waiting was both correct and free. `databricks
pipelines stop <id>` is available but spends a second run's compute for no new
information.

**Lesson.** After a pipeline failure, check whether it is already retrying
before launching anything. Confirm what is actually deployed with
`databricks workspace export <path>` rather than trusting the local file — they
diverge whenever an edit has not been followed by `bundle deploy`.

### E20 — a scratch mutation script left the repo modified {#e20}

**No error surfaced to the user.** The script crashed with `FileNotFoundError`
on a wrong interpreter path — and its restore step never ran, so
`scripts/upload.ps1` sat on disk with `immunizations` deleted. Exactly the
condition of [E15](#e15), reintroduced by the tooling written to prevent it.

**Cause.** Mutate, test, restore — written as three sequential statements. Any
failure between the first and third leaves the mutation in place.

**Fix.** `try/finally`, so the restore runs whether or not the test does. The
corrected version caught both mutants and the full suite confirmed the files
were back.

**Lesson.** Second entry in a row about the verification rather than the code
([E16](#e16) was the first). Anything that deliberately breaks a file to check a
test must restore it in a `finally`, and the check that it restored correctly is
running the full suite afterwards.

---

## Task 8 — snapshot publish

### E21 — `KeyError: 'DATABRICKS_HOST'` with a fully populated `.env` {#e21}

```
host = os.environ["DATABRICKS_HOST"].replace("https://", "").rstrip("/")
KeyError: 'DATABRICKS_HOST'
```

**Cause.** **`.env` is a file, not an environment.** Nothing loads it into
`os.environ`. The plan created `.env`, wrote `os.environ[...]` in the scripts,
and never connected the two — no document in the repo mentioned `dotenv`,
`load_dotenv`, `set -a` or `export`.

**Why it did not surface in Task 5.** `run_sql.py` carries the identical bug. It
only worked because that shell happened to have the variables exported.
**Working by accident of shell state is indistinguishable from working**, right
up until a different shell runs it.

**Fix.** `python-dotenv`, plus `scripts/dbx.py` as the single place that loads
the file and opens a connection. Both callers now go through it, so the next
script cannot forget. → [D24](decision.md)

**Second defect, found while fixing the first.** The original raises on
whichever variable is read first. With all three absent it still names only
`DATABRICKS_HOST`, sending you to check one setting when three are missing.
`dbx.connect()` reports the full list and points at `.env.example`.

**Note.** A bug in the *plan*, the sixth. This one is the most instructive of
them: the plan was internally consistent — create `.env`, read `os.environ` —
and simply omitted the step that joins the halves. **Reference code is not
executed code**, and a missing step leaves no trace to review against.

---

## Patterns

Twenty-one entries, and they fall into four shapes.

**1. Silent wrongness is the real enemy — E3, E6, E7, E8, E14, E15, E16, E20.**
Eight of twenty produced no failure signal at all. Every one of them would have shipped a
plausible wrong number. The crashes in this file cost minutes; these are the
ones that would have cost the project its credibility. **A tool that cannot
fail cannot be trusted when it succeeds** — and E16 shows the rule applies to
the verification commands too, not just the code under test.

**2. Errors in the plan, not the typing — E4, E6, E9, E10, E18, E21.**
Six came from reference code and expectations written before anything ran, and
E21 is the sharpest: the plan was internally consistent and still wrong, because
it omitted the step joining two halves it had each written correctly.
Written code is a hypothesis until it executes. When one of these is found, the
plan gets fixed too, or the next person retypes the bug.

**3. Windows-specific environment friction — E5, E11, E12.**
`Scripts/` not `bin/`, cp1252 not UTF-8, PATH snapshotted at process start.
None are deep, all cost time, all recur.

**4. Two things with one name — E1, E10, E12, E17.**
pyarrow pinned in two places with different opinions; three different products
called "databricks"; venv layouts that differ by platform; `cloudFile` versus
`cloudFiles`. The fix is always the
same: find out which one you actually have before theorising about why it is
broken.
