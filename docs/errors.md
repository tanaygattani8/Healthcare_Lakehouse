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
| [E22](#e22) | `I001 Import block is un-sorted` on already-committed code | 10 |
| [E23](#e23) | `Failed to download and build pyarrow==16.1.0` on Streamlit Cloud | 9 |
| [E24](#e24) | `RESOURCE_EXHAUSTED: Cannot create the resource` on pipeline run | 2a-0 |
| [E25](#e25) | `Triggering new runs for organization … is currently disabled temporarily` | 2b-1 |
| [E26](#e26) | Docker Desktop: "virtualisation support wasn't detected" | 2b-3 |
| [E27](#e27) | `500 Internal Server Error for API route … dockerDesktopLinuxEngine` mid-build | 2b-3 |
| [E28](#e28) | Docker won't start: `rename … .sock … The file cannot be accessed by the system` | 2b-3 |
| [E29](#e29) | Rebuilt jar's manifest says `Build-Version: N/A` | 2b-3 |
| [E30](#e30) | Container run: `Records: total=1138`, `OutOfMemoryError`, exit 0 | 2b-3 |
| [E31](#e31) | Same seeds, different dataset — `1147`, every table off | 2b-3 |
| [E32](#e32) | First DAG run: `httpx.ReadTimeout: timed out`, task never started | 2b-5 |
| [E33](#e33) | CI tab is empty. `actions/runs` returns `"total_count": 0` | 2b-0 |
| [E34](#e34) | `PARSE_SYNTAX_ERROR at or near 'after'` — half an English sentence | 3a |
| [E35](#e35) | `UC_INVALID_POLICY_CONDITION … Unknown tag policy key` | 3a |
| [E36](#e36) | Same error, seconds after creating that exact governed tag | 3a |
| [E37](#e37) | `column_masks` empty although masking demonstrably works | 3a |
| [E38](#e38) | A renamed function exists under both names | 3a |

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

## Task 10 — README

### E22 — a lint violation found in code committed two commits ago {#e22}

```
app\streamlit_app.py:1:1: I001 [*] Import block is un-sorted or un-formatted
```

**Cause.** One trailing space after `import pandas as pd`. Ruff's `I` rules
treat the import block as a single unit, so trailing whitespace inside it
reports as an *ordering* violation — the message names the wrong defect, which
is why the file looks perfectly correct when you read it.

**Where it came from.** `app/streamlit_app.py` was committed in `f382b4c`
without `ruff check .` running first. The linter did not miss it; the linter
was not asked.

**Fix.** `ruff check . --fix`. One character.

**Note.** The second occurrence of the same shape as [E16](#e16) — a commit
landing with a lint gate that never ran. E16 was the gate's *exit code* being
swallowed by a pipe; this one is the gate being skipped outright. Both end in
the same place: `main` holding code the project's own standard rejects. Nothing
in the repo enforces the gate yet. A pre-commit hook is the obvious fix and is
deliberately not built — phase 2 brings CI, which is where it belongs.

---

## Task 9 — the public app

### E23 — `pyarrow` fails to build on Streamlit Community Cloud {#e23}

```
× Failed to download and build `pyarrow==16.1.0`
  ╰─▶ Build backend failed to determine requirements with `build_wheel()`
      ModuleNotFoundError: No module named 'pkg_resources'
```

**`pkg_resources` is the last domino, not the cause.** Pinning setuptools would
get past it and straight into compiling Arrow C++ from source on a free build
box, which fails differently and slower.

**Cause, in order.**

1. Streamlit Cloud built the app on **Python 3.14.7**. Local development is on
   **3.12.1**. The interpreter was never pinned, so Cloud used its default.
2. Cloud read the **root `requirements.txt`** — every dependency in the project,
   including `databricks-sql-connector==3.4.0`.
3. That connector caps pyarrow at `<17`. The `pyarrow` line is deliberately
   unpinned ([D3](decision.md)), so the resolver took the highest still allowed:
   **16.1.0**.
4. pyarrow 16.1.0 predates Python 3.14. **No cp314 wheel exists**, so uv fell
   back to a source build.
5. The source build imports `pkg_resources`, which modern setuptools no longer
   ships on 3.14.

**Not one bad pin — the whole set.** Further down the same log,
`pandas-2.2.3.tar.gz` and `duckdb-1.1.3.tar.gz (12.2 MB)` are also source
tarballs. Neither has a cp314 wheel either. Fixing pyarrow alone would have
surfaced pandas next.

**The comment that predicted it.** `requirements.txt` already carried a note
explaining that `databricks-sql-connector` constrains the pyarrow range. It was
written to justify leaving pyarrow unpinned. It turned out to name the exact
constraint that broke the deploy — **a documented constraint is not a contained
one**.

**The real defect.** `app/streamlit_app.py` imports `pathlib`, `pandas` and
`streamlit`. It reads a committed Parquet snapshot and never opens a warehouse
connection — that is the whole point of the snapshot design. Yet the deployment
was installing a database engine and a SQL driver it will never call, and one of
them is what broke the build. The dependency that has no reason to be there is
the dependency that failed.

**Fix.** `app/requirements.txt` listing only the three packages the app imports.
Streamlit Cloud searches the entrypoint's directory before the repo root, so it
wins at deploy time and the root file is untouched for local work.
→ [D25](decision.md)

**Round two — the same message, a new cause.** The next build proved the file
was found (`-r /mount/src/healthcare_lakehouse/app/requirements.txt (line 14)`,
41 packages resolved instead of 53) and then failed on `pyarrow==16.1.0` again.
`app/requirements.txt` pinned that version **by hand**, one line below a comment
explaining that 16.1.0 is exactly the version with no cp314 wheel. Removing
`databricks-sql-connector` removed the *reason* 16.1.0 was selected; writing the
number in manually reinstated the result. **A constraint deleted and a constraint
re-typed are the same constraint.**

**Real fix.** The pins were never the problem — the interpreter was. Streamlit
Cloud → app menu → **Settings → General → Python version**, changed from 3.14 to
**3.12**, matching local development. Save rebuilt the app in place. Every pin
has a cp312 wheel, so nothing was downloaded as source and nothing was
recompiled.

**A wrong recommendation, corrected by looking.** The documented procedure —
and what was recommended here — was to *delete the app and redeploy*, because
the Python version was historically fixed at deploy time. The settings dialog
now has an editable dropdown offering 3.10 through 3.14. **The docs described a
version of the product that no longer exists.** Opening the dialog before
deleting cost one click and saved an irreversible one.

**Rule this leaves behind.** When a fix requires destroying something, open the
settings screen first. Documentation ages; the UI is the current truth.

---

## Phase 2a Task 0 — multi-schema spike

### E24 — `RESOURCE_EXHAUSTED` starting the pipeline cluster {#e24}

```
Failed to create a cluster because you've exceeded resource limits:
RESOURCE_EXHAUSTED: Cannot create the resource, please try again later.
```

**What this is not.** It is not a bug in the code, the bundle or the spike.
`ruff` passed, `bundle validate -t dev` passed, `bundle deploy -t dev` succeeded
and updated the pipeline. The failure is at cluster creation — before a line of
pipeline code runs.

**Two candidate causes, and the message does not distinguish them.**

1. Free Edition compute quota consumed, which locks compute for a period.
2. Transient serverless capacity shortage in the workspace's pool.

The evidence leans to (2): **nothing had been run that day.** The previous
pipeline update was five days earlier and no warehouse had been woken. A quota
story requires consumption that did not happen. "Please try again later" is also
capacity phrasing rather than quota phrasing. Not conclusive.

**Do not diagnose this by probing.** The obvious next move — query a bronze
table to see whether *anything* can get compute — wakes the SQL warehouse and
consumes the very resource in question. If cause (1) is real, the diagnostic
makes it worse. Wait instead.

**The pipeline retries itself.** As in [E19](#e19), a `CREATED` update appeared
seconds after the two `FAILED` ones with no human action. Checking the pipeline
state immediately after a failed `bundle run` will show `RUNNING` — that is the
retry, not a second submission, and starting another run on top of it produces
"An active update already exists".

**Retried twenty minutes later. Identical failure.** Not a momentary spike, then
— but still not proof of quota, because a capacity shortage can last hours. The
test that separates the two is a run after a long idle period: if it fails after
a night of zero usage, it is not consumption-based.

**What it did not block.** Everything in phase 2a that does not need a cluster
still ran: the local DuckDB exploration of all eighteen CSVs
(`silver-model-findings.md`), `ruff`, `pytest`, and `bundle validate` against
both targets. `validate` reaches the workspace API without starting compute,
which is why the CI workflow is useful even while the workspace cannot run
anything.

**Resolved after ~35 minutes, cause not fully established.**

The decisive fact: **the SQL warehouse started and ran `SELECT 1` while the
pipeline could not get compute.** So the account was never locked out and this
was never the daily-quota lockout the project has been braced for. Whatever was
exhausted, it was not the whole workspace.

"Failed to create a cluster" is also Databricks' internal wording. Free Edition
is serverless-only — there is no cluster to create, size or configure, and
nothing in that sentence is user-actionable.

Sequence, for honesty about what is and is not proven:

| Time | Event |
|---|---|
| 23:02 | pipeline run FAILED, warehouse state unknown |
| 23:16 | retry FAILED |
| ~23:30 | warehouse started, `SELECT 1` succeeded |
| ~23:35 | warehouse stopped |
| 23:37 | pipeline run **COMPLETED** |

Two explanations fit. Either the warehouse was holding capacity the pipeline
needed, or the shortage was transient and simply passed. **Stopping the
warehouse is correlated with the success but is not proven to have caused it** —
the 23:16 retry probably ran with no warehouse up, and still failed. Do not
record this as "stop the warehouse to fix it"; record it as "not a lockout, it
cleared on its own timescale".

**The practical rule.** When pipeline compute is refused, check whether a
warehouse can start before concluding anything. That one query separates "the
workspace is locked for the day" from "this resource is briefly unavailable",
and those two have completely different responses.

---

## Phase 2b Task 1 — submitted run

### E25 — `Triggering new runs for organization … is currently disabled temporarily` {#e25}

```
$ databricks jobs submit --json @submit.json
Error: Triggering new runs for organization 7474655569061305 is currently disabled temporarily.
```

**Not the request.** The JSON was never read — the refusal is for the whole
organization (the workspace), before validation. Nothing in the file or the
command was wrong: the identical command, unchanged, succeeded the next day.

**Cause not established.** Free Edition throttling or a quota window are the
likely candidates; the message names neither. It is a different message from
[E24](#e24) and was not diagnosed by probing, for E24's reason.

**Cleared on its own within a day** (failed 17 Sep, succeeded 18 Sep 15:49).
Work that needed no Databricks — the Synthea image and Airflow files — carried
on meanwhile.

**Rule.** "Disabled temporarily" means wait, not retry. Repeated submits against
a throttle are at best useless.

---

## Phase 2b Task 3/4 — Docker on Windows

### E26 — Docker Desktop: "virtualisation support wasn't detected" {#e26}

```
Docker Desktop failed to start because virtualisation support wasn't detected.
```

**The message points at the wrong layer.** It reads like a BIOS problem. It was
not:

```
systeminfo | findstr /i "Hyper-V Virtualization hypervisor"
    Virtualization Enabled In Firmware: Yes
```

Firmware was fine. What was missing was **Windows'** half: the WSL and Virtual
Machine Platform features, which Docker Desktop on Windows 11 Home runs inside.
No `A hypervisor has been detected` line in that output was the tell.

**Fix**, in an Administrator prompt, then a restart:

```
bcdedit /set hypervisorlaunchtype auto
wsl --install --no-distribution
```

Verified by `wsl --status` (default version 2) and `docker run --rm hello-world`
exiting 0.

**Two traps on the way.** `systeminfo | Select-String …` fails in Command
Prompt — `Select-String` is PowerShell; use `findstr /i` in `cmd`. And the first
`hello-world` check was run as `docker run … | Select-Object -First 3`, which
closed the pipe after three lines and killed the image pull mid-download — an
[E16](#e16) repeat: a truncating pipe on a verification command. Rerun bare.

### E27 — `request returned 500 Internal Server Error for API route … dockerDesktopLinuxEngine` mid-build {#e27}

```
request returned 500 Internal Server Error for API route and version
http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/_ping
```

**Cause: two builds in parallel on an 8 GB laptop.** The Synthea build (a clone
of Synthea's full history, then Gradle) and the Airflow image build were started
together. Host RAM was 7.9 GB total, 1.1 GB free; Docker's VM is capped at
~4 GB (`hv_balloon: Max. dynamic memory size: 4022 MB` in `vm/init.log`). The
VM's log stops mid-clone and the engine stopped answering.

**Fix.** One Docker build at a time on this machine. And the clone was replaced
by a single-commit fetch (`git fetch --depth 1 origin <sha>`) — the build needs
one commit, not Synthea's history.

**Orphaned builds.** Stopping the shell that launched `docker build` does **not**
stop the `docker.exe` client on Windows — the build carries on, invisible, still
writing to the same log. It happened twice here and produced a log with two
interleaved builds in it. Before starting a build, check for survivors:

```
Get-CimInstance Win32_Process -Filter "Name='docker.exe'" | Select ProcessId,CommandLine
```

Stopping that client process (`Stop-Process -Id <pid>`) cancels its build and is
safe; it is not Docker Desktop.

### E28 — Docker Desktop won't start: `rename … sailor-ingest.sock … The file cannot be accessed by the system` {#e28}

```
starting services: initializing Ingest server: listening on
unix://C:/Users/<HOST>/AppData/Local/Docker/run/sailor-ingest.sock: rename …
sailor-ingest.sock.stale: The file cannot be accessed by the system.
```

**Self-inflicted, while recovering from E27.** Docker Desktop was restarted by
force-killing its processes (`Stop-Process -Force`) plus `wsl --shutdown`. That
left Unix-socket files (0-byte reparse points) behind that Windows would then
neither delete nor let Docker rename.

**What did not work.** `Remove-Item -Force` and `cmd /c del /f` both: "The file
cannot be accessed by the system." Renaming the containing folder aside worked,
and Docker then failed identically on the next socket, in
`%LOCALAPPDATA%\docker-secrets-engine\engine.sock`. Chasing sockets one folder
at a time is whack-a-mole.

**Fix: restart Windows.** It releases every stale socket at once; Docker started
cleanly afterwards. The two folders renamed aside
(`Docker\run.stale-20260918`, `docker-secrets-engine.stale-20260918`) are
disposable — but even after the restart Windows still could not delete the
sockets inside them. `Docker\run.stale-20260918` went away when deleted from a
Linux container that mounted its parent folder. `docker-secrets-engine.stale-20260918`
did not: `Remove-Item`, `rmdir /s /q`, a container mount and the `docker-desktop`
WSL distro all failed or saw an empty folder. Two 0-byte entries remain in
AppData; harmless, left alone.

**Rule.** Quit Docker Desktop from its tray menu. Never force-kill it.

### E29 — rebuilt Synthea jar says `Build-Version: N/A` {#e29}

Silent: the build succeeded and the jar ran. Only reading its manifest showed
it:

```
original  Build-Version: 7e08387
rebuilt   Build-Version: N/A
```

**Cause.** Synthea's `build.gradle` reads `src/main/resources/version.txt` into
the manifest when the jar task is *configured*, but the task that writes that
file (via `git describe --tags --always`) runs later. A fresh checkout never has
the file in time, so the stamp falls back to `N/A`. Synthea's own CI build had
it from an earlier step. The file is also packaged into the jar, so this is not
only a label.

**Fix.** The Dockerfile writes `version.txt` itself with the same command before
running Gradle. Rebuilt jar: `Build-Version: 7e08387` and `version.txt` =
`7e08387`, matching the original on both. Size 197,024,930 bytes against the
original's 197,024,912 — identical code, different embedded timestamps.

**Why it mattered.** The image exists to pin a version.

### E30 — container generates 1,138 patients, not 1,148, and exits 0 {#e30}

```
java.lang.OutOfMemoryError: Java heap space      (repeated)
Records: total=1138, alive=995, dead=143
exit=0
```

**Silent wrongness, the worst kind in this file.** The run finished, printed a
cheerful "You've just generated 1138 patients!", and returned success. Ten
patients were missing, and nothing but the count said so.

**Cause.** The JVM defaults its heap to a quarter of the memory it can see.
Inside Docker Desktop's ~4 GB VM that is ~1 GB; the recorded run on the laptop
had ~2 GB (a quarter of 8 GB). Synthea generates patients on worker threads; a
thread that runs out of heap loses that patient and the run carries on.

**Fix.** `-Xmx3g` in the image's entrypoint. Heap size does not change what a
seed generates — only whether generation survives.

**Rule.** Check `Records: total=… alive=… dead=…` against the recorded
`1148 / 1000 / 148`, and search the log for `OutOfMemoryError`, before trusting
any generation run. Exit code 0 means nothing here.

### E31 — same jar, same seeds, same config, different dataset {#e31}

With E30 fixed, the container still did not reproduce `calibration.md`:

```
Records: total=1147, alive=1000, dead=147        (recorded: 1148 / 1000 / 148)
encounters 189,032 (recorded 187,540) · organizations 825 (826) · every table off
```

**Not the seeds.** 1,143 of 1,147 patient `Id`s matched the recorded run —
the seeds reached the jar. But only 893 matched on name and birth date, and
tables that do not depend on patients (organizations, providers) differed too.

**Cause, from diffing the two runs' `metadata/*.json`.** Every setting matched
except one:

```
endTime   recorded: 20260808    container: 20260918
```

**Synthea simulates every life up to the day it is run.** `-r` fixes the
reference date; it does not fix the end. The recorded dataset stops on 8 Aug
2026; the container ran on 18 Sep and simulated six more weeks — more
encounters, different deaths, and a different population drawn from the same
seeds.

**This was wrong since phase 1.** `synthea/README.md` said the three seeds were
sufficient for reproducibility. They were never sufficient: the recorded
command, rerun on any later day, gives a different dataset. Nobody had rerun it
until now, which is the only reason it went unnoticed.

**Fix.** `-e 20260808` in the image's entrypoint — the recorded run's own date,
read from its metadata — and the README corrected. Synthea at this commit
accepts `-e endDate as YYYYMMDD`.

**It was not the whole story.** With `-e`, 861 of 1,148 patients matched.
Single-threaded generation gave the identical result (threading ruled out). The
remaining cause was the **timezone**: the recorded run was on a Central-time
laptop, the container is UTC, and Synthea turns timestamps into dates in the
JVM's zone. With `-Duser.timezone=America/Chicago`: 1,148 patients, 1,136
identical, 132 rows of 3.28 million different — all in the final weeks, from
`-e` stopping at midnight where the recorded run stopped at 22:18. D35.

**The general lesson.** Seeds pin the random numbers. They do not pin the
clock, the calendar or the timezone, and a simulator reads all three. A jar that cannot say
which version it is defeats the pin even when the code inside is right.

---

## Phase 2b Task 5 — the DAG

### E32 — first DAG run fails in under a minute: `httpx.ReadTimeout: timed out` {#e32}

```
[error] Workload execution failed.  [airflow.executors.local_executor.LocalExecutor]
httpx.ReadTimeout: timed out
Executor LocalExecutor reported that the task instance … finished with state
failed, but the task instance's state attribute is queued.
```

**Never reached Databricks.** No run was submitted. In Airflow 3 a task's first
act is an HTTP call to the API server's `/execution/` endpoint to say it has
started. That call timed out.

**Cause: triggered before the API server had finished starting.** Its log shows
`Waiting for application startup` at 02:14:52 and the first request served at
02:18:21 — three and a half minutes, with the scheduler and DAG processor still
`health: starting` alongside it on a 4 GB VM. The task's call waited 78 s.
`/api/v2/monitor/health` had already answered 200, which is why it looked ready.

**Fix: wait for every service to report `(healthy)` in
`docker compose ps`, not just the health URL.** The identical trigger, five
minutes later, succeeded.

**Also on Windows:** task log files are named `run_id=manual__2026-09-19T02:16:53…`
— colons, which Windows cannot open (`OSError: [Errno 22] Invalid argument`).
Read them inside the container:
`docker compose exec airflow-scheduler cat "/opt/airflow/logs/dag_id=…/attempt=1.log"`,
or in the web UI.

---

## Phase 2b Task 0 — the PR check gate

### E33 — the CI gate has never run, and nothing said so {#e33}

`.github/workflows/pr.yml` was added in `07f6d90` to stop broken code reaching
main after E16 and E22. Phase 2b's Task 0 was to confirm it goes green on a
clean branch and red on a broken one.

Checking for the dates of those two runs, the GitHub API says there are none:

```
$ curl -s ".../actions/runs?per_page=50"
{ "total_count": 0, "workflow_runs": [] }

$ curl -s ".../pulls?state=all"
[]
```

The workflow itself is registered and `"state": "active"`, created
2026-09-15T22:45:15Z. It has simply never been triggered.

**Cause: the trigger is `on: pull_request`, and no pull request has ever been
opened on this repository.** Every commit in the history went straight to
`main` — including the three that closed phase 2b. The gate cannot fire on a
push it never sees.

So the state of the gate is unknown in both directions. It has never been seen
green, so it is not known to work; never seen red, so it is not known to catch
anything. A workflow file in the repo reads like protection and is currently
decoration. **This is the same shape as E16**: the check that was supposed to
prove correctness was itself never verified.

**Not fixed yet.** Two options, and they are not equivalent:

| | |
|---|---|
| Open a real PR from a throwaway branch | Tests the gate exactly as it will be used. Costs one Databricks token round-trip in the `bundle` job. |
| Add `push: branches: [main]` to the trigger | Makes the gate fire on the workflow this project actually uses, but it runs *after* the bad commit has landed — it reports, it does not gate |

The first proves the mechanism. The second matches reality: solo work on
`main`, with no PR in the loop. Doing only the second means the lint job that
exists because of E16 reports a failure that is already in history.

Recorded rather than fixed because it is a phase-3a decision, not a phase-2b
loose end.

---

## Phase 3a — PHI governance

### E34 — half an English sentence arrives at the warehouse as SQL {#e34}

```
[PARSE_SYNTAX_ERROR] Syntax error at or near 'after'
== SQL ==
after tagging it would orphan them.
```

`run_sql.py` split statements with `text.split(";")`. The file's header comment
read *"Safe to run now because no column carries this tag yet; after tagging it
would orphan them."* The semicolon inside that sentence was treated as a
statement terminator. The first fragment was comment-only and filtered out; the
second had no `--` prefix, so it looked like SQL.

**The `ALTER` had already succeeded.** The script still exited non-zero, so the
run looked like a failure when the work was done — the inverse of
[E14](#e14), and just as misleading.

**Fix:** `_statements` now treats `;` as a terminator only where it appears
before any `--` on that line. Three tests in `tests/test_run_sql.py`. The code
comment had warned about exactly this case since phase 1 and it was still
written into a file the same day it was read.

---

### E35 — `Unknown tag policy key` on a tag that plainly exists {#e35}

```
INVALID_PARAMETER_VALUE.UC_INVALID_POLICY_CONDITION
Invalid condition in policy 'probe_ssn_mask'.
Compilation error with message 'Unknown tag policy key `phi_category`'
```

`ALTER … SET TAGS ('phi_category' = 'ssn')` had succeeded and
`information_schema.column_tags` showed the row.

**Cause: two different things are called tags.** `SET TAGS` writes a free-form
key-value pair and accepts any key. ABAC policies match only **governed tags** —
account-level keys registered with `CREATE GOVERNED TAG`, carrying a declared
value list. A free-form tag is invisible to `has_tag_value`.

**Fix:** register the key first. Pattern 4 in this file, fourth instance.

---

### E36 — the same error, immediately after creating that governed tag {#e36}

`governance_row_filter.sql` runs `CREATE GOVERNED TAG row_scope`, tags a column
with it, then creates a policy matching it. The policy failed with E35's
message naming `row_scope` — in the same script, seconds later. Re-running the
policy statement alone succeeded, unchanged, with nothing else altered.

**Cause: a new governed tag is not immediately visible to the policy compiler.**
Governed tags are account-level and the policy compiles against a separate
view of them.

**Consequence for any bootstrap file:** registering a governed tag and creating
a policy that matches it cannot be one script. Split them, or accept that the
first run of a combined file always fails at the policy and must be re-run.

---

### E37 — `column_masks` is empty while masking demonstrably works {#e37}

`SELECT count(*) FROM information_schema.column_masks` returned 0, with four
column mask policies live and `SSN` visibly returning `***`.

**Not a bug — the wrong catalog.** `column_masks` records masks attached with
`ALTER COLUMN … SET MASK`. A mask applied by an ABAC policy is recorded in
`abac_policy_definitions` and nowhere else.

**Why it mattered.** The tag-versus-mask drift check validated in
[decision.md](decision.md) D42 joined `column_tags` to `column_masks`. Under the
ABAC design adopted one decision later, that check reports **all 19 tagged
columns as unprotected, permanently**. It was verified failing-on-purpose and
passing — against a design that was then replaced, and the verification was not
re-run.

**A check that always fails is worse than no check**, because it trains its
reader to ignore it. Rewritten against `abac_policy_definitions`, and re-proven
in both directions by dropping `mask_phi_zip` and watching `zip` appear.

---

### E38 — a renamed function exists under both names {#e38}

`mask_name` was renamed to `mask_text` in `governance_bootstrap.sql`. The file
said `mask_text`. `information_schema.routines` said `mask_name`.

**Cause: the edited file was never re-run**, and `CREATE OR REPLACE FUNCTION`
does not rename — re-running would have produced *both*, leaving the old one
behind for any policy still pointing at it.

**Nothing reports this.** The file and the catalog are separate states with no
reconciliation between them. The drift check (E37) compares tags against
policies, not files against catalog. Caught only because
`routines` was queried for an unrelated reason.

**Fix:** re-run the file, then `DROP FUNCTION` the orphan. The general problem
stands: **for governance, the SQL file is not the source of truth, the catalog
is** — and only the catalog was ever tested.

---

## Patterns

**1. Silent wrongness is the real enemy — E3, E6, E7, E8, E14, E15, E16, E20, E22, E29, E30, E31, E33, E37, E38.**
Fifteen of thirty-eight produced no failure signal at all. Phase 2b added four:
a jar that could not name its version, a run that dropped ten patients
and exited 0, a "reproducible" command that had never been reproducible, and a
CI gate that had never run once. Phase 3a added two more, both in the
governance layer itself — a drift check that would have reported every
protected column as unprotected forever, and a function the file and the
catalog disagreed about. Every one of them would have shipped a
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

**3. Windows-specific environment friction — E5, E11, E12, E26, E27, E28, E32.**
`Scripts/` not `bin/`, cp1252 not UTF-8, PATH snapshotted at process start.
Phase 2b added Docker's: WSL missing behind a BIOS-sounding message, 4 GB for
everything, sockets that survive a force-quit, orphaned `docker.exe` clients,
log filenames with colons. None are deep, all cost time, all recur.

**4. Two things with one name — E1, E10, E12, E17.**
pyarrow pinned in two places with different opinions; three different products
called "databricks"; venv layouts that differ by platform; `cloudFile` versus
`cloudFiles`. The fix is always the
same: find out which one you actually have before theorising about why it is
broken.
