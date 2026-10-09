# archive

One-off files, kept as the record their decisions cite; nothing re-runs them.

- `sql/probe_*.sql`, `notebooks/probe_*.py`, `notebooks/p5*.py`, `notebooks/p6_*.py`:
  the probes run before a phase was planned, to test what the platform would
  do rather than assume it. Each is cited by the decision it shaped
  (`docs/decision.md`).
- `sql/phase7_*.sql`, `sql/phase8_*.sql`: before and after fingerprints and
  the cleanup of a phase's throwaway objects.

Moved here from `sql/` and `notebooks/` after the audit (D81), so the two
folders hold only what the pipeline, governance and model actually run.
Archived notebooks no longer run with `scripts/run_notebook.sh`, which looks
in `notebooks/`.
