""" Measure a Synthea output directory and produce a markdown report.

Row counts, not patient counts, are what size this project. Synthea writes a
full birth-to-death record per patient, so per-entity row counts run an order
of magnitude above intuition. Everything downstream is sized from this report.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import duckdb

from scripts.entities import ENTITIES


def measure_file(con: duckdb.DuckDBPyConnection, path: Path) -> dict:
    """Row count and byte size for one CSV. Does not load the file into memory"""
    rows = con.execute(
        "SELECT count(*) FROM read_csv_auto($1, header=true)", [str(path)]
    ).fetchone()[0]
    return {"file": path.name, "rows": rows, "bytes": path.stat().st_size}


def parquet_bytes(con: duckdb.DuckDBPyConnection, path: Path, tmp_dir: Path) -> int:
    """Size of the same data as Parquet.

    Delta stores Parquet, so raw CSV bytes overestimate lakehouse storage
    several-fold. Quota planning needs this number, not the CSV one.
    """
    out = tmp_dir / f"{path.stem}.parquet"
    con.read_csv(str(path), header=True).write_parquet(str(out))
    return out.stat().st_size


def distinct_codes(con: duckdb.DuckDBPyConnection, path: Path, code_col: str = "CODE") -> int:
    """Distinct terminology codes in a file. Returns 0 if the column is absent."""
    columns = con.execute(
        "SELECT * FROM read_csv_auto($1, header=true) LIMIT 0", [str(path)]
    ).description
    if code_col not in {c[0] for c in columns}:
        return 0
    return con.execute(
        f"SELECT COUNT(DISTINCT {code_col}) FROM read_csv_auto($1, header=true)", [str(path)]
    ).fetchone()[0]


def note_stats(notes_dir: Path) -> dict:
    """Count, disk size and character-length spread of the clinical notes.

    Bytes are here because the notes outweigh every entity CSV combined and
    phase 3 reads all of them, so a quota estimate that omits them is wrong.
    Max is here because the mean understates it by an order of magnitude, and
    it is the max that sizes the context window a de-identification model needs.
    """
    files = [p for p in notes_dir.iterdir() if p.is_file()] if notes_dir.is_dir() else []
    lengths = [len(p.read_text(encoding="utf-8", errors="replace")) for p in files]
    if not lengths:
        return {"note_count": 0, "total_bytes": 0, "mean_chars": 0.0, "max_chars": 0}
    return {
        "note_count": len(lengths),
        "total_bytes": sum(p.stat().st_size for p in files),
        "mean_chars": sum(lengths) / len(lengths),
        "max_chars": max(lengths),
    }


def render_markdown(rows: list[dict], patient_count: int, notes: dict) -> str:
    lines = [
        "# Calibration — dev tier",
        "",
        f"Patients generated: **{patient_count:,}**",
        "",
        "| File | Rows | Rows per patient | CSV bytes | Parquet bytes | Distinct codes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(rows, key=lambda x: -x["rows"]):
        per_patient = r["rows"] / patient_count if patient_count else 0.0
        lines.append(
            f"| {r['file']} | {r['rows']:,} | {per_patient:.1f} "
            f"| {r['bytes']:,} | {r['parquet_bytes']:,} | {r['distinct_codes']:,} |"
        )
    total_rows = sum(r["rows"] for r in rows)
    total_bytes = sum(r["bytes"] for r in rows)
    total_parquet = sum(r["parquet_bytes"] for r in rows)
    lines += [
        "",
        f"**Total rows:** {total_rows:,}  ",
        f"**Total CSV bytes:** {total_bytes:,}  ",
        f"**Total Parquet bytes:** {total_parquet:,}",
        "",
        "## Clinical notes",
        "",
        f"Notes: **{notes['note_count']:,}**, **{notes['total_bytes']:,}** bytes on disk.  ",
        f"Length in characters — mean **{notes['mean_chars']:,.0f}**, "
        f"max **{notes['max_chars']:,}**.",
        "",
        "Note bytes are *not* included in the totals above. Phase 3 reads this",
        "corpus in full, so add it to any quota estimate. Size the de-identification",
        "context window from the max, not the mean.",
        "",
        "## Extrapolation to the main tier",
        "",
        "Multiply *rows per patient* by the target population. Size storage from",
        "the **Parquet** column, not the CSV one — Delta stores Parquet. Check the",
        "result against the Free Edition quota **before** generating it: exceeding",
        "quota shuts down workspace compute for the rest of the day.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("synthea/output"))
    parser.add_argument("--report", type=Path, default=Path("docs/calibration.md"))
    args = parser.parse_args()

    con = duckdb.connect()
    csv_dir = args.output_dir / "csv"

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for entity in ENTITIES:
            path = csv_dir / f"{entity}.csv"
            if not path.exists():
                print(f"skipping {path.name} — not found")
                continue
            measured = measure_file(con, path)
            measured["parquet_bytes"] = parquet_bytes(con, path, tmp_dir)
            measured["distinct_codes"] = distinct_codes(con, path)
            rows.append(measured)

    # Without this, a wrong --output-dir writes a structurally valid report full
    # of zeros over the committed one and exits 0. This report is the sizing
    # authority for every later phase; a plausible-looking wrong one is worse
    # than a crash.
    if not rows:
        raise SystemExit(f"no entity CSVs found under {csv_dir}")

    patient_count = next((r["rows"] for r in rows if r["file"] == "patients.csv"), 0)
    notes = note_stats(args.output_dir / "notes")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_markdown(rows, patient_count, notes), encoding="utf-8")
    print(f"wrote {args.report}")


if __name__ == "__main__":
    main()     
