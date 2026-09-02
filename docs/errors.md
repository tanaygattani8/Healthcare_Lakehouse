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

## Patterns

Sixteen entries, and they fall into four shapes.

**1. Silent wrongness is the real enemy — E3, E6, E7, E8, E14, E15, E16.**
Seven of sixteen produced no failure signal at all. Every one of them would have shipped a
plausible wrong number. The crashes in this file cost minutes; these are the
ones that would have cost the project its credibility. **A tool that cannot
fail cannot be trusted when it succeeds** — and E16 shows the rule applies to
the verification commands too, not just the code under test.

**2. Errors in the plan, not the typing — E4, E6, E9, E10.**
Four came from reference code and expectations written before anything ran.
Written code is a hypothesis until it executes. When one of these is found, the
plan gets fixed too, or the next person retypes the bug.

**3. Windows-specific environment friction — E5, E11, E12.**
`Scripts/` not `bin/`, cp1252 not UTF-8, PATH snapshotted at process start.
None are deep, all cost time, all recur.

**4. Two things with one name — E1, E10, E12.**
pyarrow pinned in two places with different opinions; three different products
called "databricks"; venv layouts that differ by platform. The fix is always the
same: find out which one you actually have before theorising about why it is
broken.
