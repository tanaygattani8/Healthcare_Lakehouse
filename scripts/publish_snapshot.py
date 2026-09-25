from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from scripts import dbx
from scripts.entities import ENTITIES

# Silver tables and the ops.quarantine_* table each one feeds. Kept here rather
# than derived from ENTITIES because silver names are singular and do not map
# one-to-one onto the bronze entity list.
SILVER_TABLES = [
    "patient", "encounter", "condition", "observation", "medication",
    "procedure", "immunization", "allergy", "careplan",
]


def build_count_query(catalog: str, entities: list[str]) -> str:
    parts = [
        f"SELECT 'bronze' AS layer, '{e}' AS entity, count(*) AS rows "
        f"FROM {catalog}.bronze.br_{e}"
        for e in entities
    ]
    parts += [
        f"SELECT 'silver', '{t}', count(*) FROM {catalog}.silver.{t}"
        for t in SILVER_TABLES
    ]
    parts += [
        f"SELECT 'quarantine', '{t}', count(*) FROM {catalog}.ops.quarantine_{t}"
        for t in SILVER_TABLES
    ]
    return "\nUNION ALL\n".join(parts) + "\nORDER BY layer, rows DESC"


def fetch_counts(catalog: str, entities: list[str]) -> pd.DataFrame:
    with dbx.connect() as conn, conn.cursor() as cur:
        cur.execute(build_count_query(catalog, entities))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["layer", "entity", "rows"])
    df["captured_at"] = dt.datetime.now(dt.UTC)
    return df


# Phase 3b: how well patient details were hidden. Both tables hold counts and
# category labels only, and check_only_categories() refuses anything else — a
# de-identification page that leaked a name would be the worst possible bug.
DEID_SNAPSHOTS = {
    "deid_scores": "SELECT stage, phi_category, real_items, guesses, precision, "
                   "recall, covered_recall, exact_recall FROM {catalog}.ops.detection_score",
    "deid_kanon": "SELECT version, k, groups, people FROM {catalog}.ops.kanon_spread",
}
ALLOWED_TEXT = {
    "stage": {"roster", "regex", "ner", "llm"},
    "phi_category": {"name", "date", "age", "geography", "other_id", "zip"},
    "version": {"plan", "safe", "released"},
    "k": {"1", "2", "3", "4", "5-10", "11+"},
}


def check_only_categories(df: pd.DataFrame) -> None:
    """Stop before writing if any text column holds a value we did not expect."""
    for column in df.select_dtypes(include="object").columns:
        unexpected = set(df[column].dropna()) - ALLOWED_TEXT.get(column, set())
        if unexpected:
            raise SystemExit(f"refusing to publish: column {column!r} has "
                             f"{len(unexpected)} value(s) that are not known categories")


def fetch_deid(catalog: str) -> dict[str, pd.DataFrame]:
    frames = {}
    with dbx.connect() as conn, conn.cursor() as cur:
        for name, query in DEID_SNAPSHOTS.items():
            cur.execute(query.format(catalog=catalog))
            df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
            check_only_categories(df)
            frames[name] = df
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="healthcare_dev")
    parser.add_argument("--out", type=Path, default=Path("snapshots/bronze_counts.parquet"))
    args = parser.parse_args()

    df = fetch_counts(args.catalog, ENTITIES)
    # Aggregates only. Quarantined rows are patient-shaped records; the public
    # page gets counts, never a sample.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(df.to_string(index=False))
    print(f"Wrote {args.out}")

    for name, frame in fetch_deid(args.catalog).items():
        path = args.out.parent / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        print(frame.to_string(index=False))
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
