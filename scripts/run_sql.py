from __future__ import annotations

import argparse
from pathlib import Path

from scripts import dbx


def _statements(text: str) -> list[str]:
    # ponytail: naive split on ';'. Fine for DDL. Breaks on semicolons inside
    # string literals or comments — switch to sqlglot if that day ever comes.
    return [s.strip() for s in text.split(";") if s.strip()]


def run_file(path: Path) -> None:
    with dbx.connect() as conn, conn.cursor() as cur:
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
    
