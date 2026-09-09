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


if __name__ == "__main__":
    main()
