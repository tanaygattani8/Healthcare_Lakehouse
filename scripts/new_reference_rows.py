"""Rewrite batch 2's reference files to hold only ids batch 1 lacks (D65); rerun-safe."""

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
