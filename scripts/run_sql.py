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
    """Where this line's statement ends, or None; ';' in a comment or string doesn't count (E34)."""
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
            # Both quote kinds: table COMMENT "..." literals hold prose.
            quote = char
        elif char == "-" and line[i : i + 2] == "--":
            return None
        elif char == ";":
            return i
        i += 1
    return None


def _statements(text: str) -> list[str]:
    # ponytail: one terminator per line, no /* */ comments; use sqlglot if that changes.
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
    # Drop a trailing comment-only chunk; the warehouse rejects it.
    return [s.strip() for s in chunks if s.strip() and not _is_comment(s)]


def run_file(path: Path) -> None:
    with dbx.connect() as conn, conn.cursor() as cur:
        for statement in _statements(path.read_text(encoding="utf-8")):
            print(f" {statement.splitlines()[0][:80]}")
            cur.execute(statement)
            # ponytail: a probe's rows are printed, capped at 20.
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
    
