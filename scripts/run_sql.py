from __future__ import annotations

import argparse
import os
from pathlib import Path

from databricks import sql

def _statements(text: str) -> list[str]:
    return [s.strip() for s in text.split(";") if s.strip()]

def run_file(path: Path) -> None:
    host = os.environ["DATABRICKS_HOST"].replace("https://", "").strip("/")
    with sql.connect(
        server_hostname=host,
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    ) as conn:
        with conn.cursor() as cur:
            for statement in _statements(path.read_text(encoding="utf-8")):
                print(f" {statement.splitlines()[0][:80]}")
                cur.execute(statement)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql_file", type=Path)
    args=parser.parse_args()
    run_file(args.sql_file)
    print(f"ran {args.sql_file}")

if __name__ == "__main__":
    main()   
    
