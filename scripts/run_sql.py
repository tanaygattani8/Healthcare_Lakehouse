from __future__ import annotations

import argparse
from pathlib import Path

from scripts import dbx


def _is_comment(statement: str) -> bool:
    return all(
        not line.strip() or line.strip().startswith("--")
        for line in statement.splitlines()
    )


def _terminator(line: str) -> int | None:
    """Where this line's statement ends, or None.

    A ';' only ends a statement when it is code — not inside a '--' comment,
    and not inside a quoted string. Both have now broken a run: prose in a
    comment (errors.md E34) and prose inside a COMMENT '...' literal.
    """
    quote = ""          # which character opened the string we are inside
    i = 0
    while i < len(line):
        char = line[i]
        if quote:
            if char == quote:
                # a doubled quote is an escape, not the end of the string
                if i + 1 < len(line) and line[i + 1] == quote:
                    i += 1
                else:
                    quote = ""
        elif char in "'\"":
            # Both kinds matter: COMMENT "..." is how this project writes
            # table comments, and those comments are English prose.
            quote = char
        elif char == "-" and line[i : i + 2] == "--":
            return None
        elif char == ";":
            return i
        i += 1
    return None


def _statements(text: str) -> list[str]:
    # ponytail: one terminator per line, and no /* block comments */. Both
    # hold for every file here — reach for sqlglot if that ever stops.
    chunks: list[str] = []
    buffer: list[str] = []
    for line in text.splitlines():
        end = _terminator(line)
        if end is None:
            buffer.append(line)
        else:
            buffer.append(line[:end])
            chunks.append("\n".join(buffer))
            buffer = [line[end + 1 :]]
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
    
