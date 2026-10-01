"""Batch 2's hospitals, doctors and insurers, less the ones batch 1 already
has (decision.md D65).

A second Synthea run with the same clinician seed reuses most reference ids.
Uploading them again would put two rows per id into bronze, so batch 2's
files are rewritten in place to hold only the new ids; for a shared id,
batch 1's row stays the one in the lakehouse. Rerunning changes nothing.

    .venv/Scripts/python.exe -m scripts.new_reference_rows synthea/output synthea/output_b2
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REFERENCE = ("organizations", "providers", "payers")


def new_rows(old_ids: set[str], rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["Id"] not in old_ids]


def main(old_dir: Path, new_dir: Path) -> None:
    for name in REFERENCE:
        with open(Path(old_dir, "csv", f"{name}.csv"), newline="", encoding="utf-8") as f:
            old_ids = {row["Id"] for row in csv.DictReader(f)}
        path = Path(new_dir, "csv", f"{name}.csv")
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        kept = new_rows(old_ids, rows)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(kept)
        print(f"{name}: {len(rows)} rows, {len(kept)} new")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
