from __future__ import annotations

import argparse
from pathlib import Path

from scripts import dbx


def _is_comment(statement: str) -> bool:
    return all(
        not line.strip() or line.strip().startswith("--")
        for line in statement.splitlines()
    )


def _statements(text: str) -> list[str]:
    # ponytail: naive split on ';'. Fine for DDL. Breaks on semicolons inside
    # string literals or comments — switch to sqlglot if that day ever comes.
    chunks = (s.strip() for s in text.split(";"))
    # A file ending in a comment leaves a trailing comment-only chunk, which
    # the warehouse rejects as a parse error after every statement succeeded.
    return [s for s in chunks if s and not _is_comment(s)]


def run_file(path: Path) -> None:
    with dbx.connect() as conn, conn.cursor() as cur:
        for statement in _statements(path.read_text(encoding="utf-8")):
            print(f" {statement.splitlines()[0][:80]}")
            cur.execute(statement)
            # A probe whose answer is a row is useless if the row is discarded.
            # ponytail: capped at 20 — this prints, it does not report.
            if cur.description:
                for row in cur.fetchmany(20):
                    print(f"    {row}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql_file", type=Path)
    args=parser.parse_args()
    run_file(args.sql_file)
    print(f"ran {args.sql_file}")

if __name__ == "__main__":
    main()   
    
