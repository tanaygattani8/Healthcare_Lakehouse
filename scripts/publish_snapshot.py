from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from scripts import dbx
from scripts.entities import ENTITIES


def build_count_query(catalog: str, entities: list[str]) -> str:
    parts = [
        f"SELECT '{entity}' AS entity, count(*) as rows FROM {catalog}.bronze.br_{entity}"
        for entity in entities
    ]
    return "\nUNION ALL\n".join(parts) + "\nORDER BY rows DESC"

def fetch_counts(catalog: str, entities: list[str]) -> pd.DataFrame:
    with dbx.connect() as conn, conn.cursor() as cur:
        cur.execute(build_count_query(catalog, entities))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["entity", "rows"])
    df["captured_at"] = dt.datetime.now(dt.UTC)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="healthcare_dev")
    parser.add_argument("--out", type=Path, default=Path("snapshots/bronze_counts.parquet"))
    args = parser.parse_args()

    df = fetch_counts(args.catalog, ENTITIES)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(df.to_string(index=False))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
