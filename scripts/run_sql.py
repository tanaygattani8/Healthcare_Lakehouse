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
    # Split on ';', but only where it is actually code. A plain text.split(';')
    # cuts prose in half the first time a comment contains a semicolon, and
    # sends the second half to the warehouse as SQL.
    # ponytail: one terminator per line, and ';' inside a string literal still
    # splits. Both are true of every file here; reach for sqlglot if that ends.
    chunks: list[str] = []
    buffer: list[str] = []
    for line in text.splitlines():
        code = line.split("--", 1)[0]
        if ";" in code:
            end = line.index(";", 0, len(code))
            buffer.append(line[:end])
            chunks.append("\n".join(buffer))
            buffer = [line[end + 1 :]]
        else:
            buffer.append(line)
    chunks.append("\n".join(buffer))
    # A file ending in a comment leaves a trailing comment-only chunk, which
    # the warehouse rejects as a parse error after every statement succeeded.
    return [s.strip() for s in chunks if s.strip() and not _is_comment(s)]


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
    
