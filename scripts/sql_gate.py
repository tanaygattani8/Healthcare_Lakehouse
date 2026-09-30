"""May this generated SQL run? Checked before every contestant's statement.

The warehouse runs as the only principal, who owns everything, so a
generated DROP TABLE would execute (spec §4). Cautious by design: harmless
text containing a blocked word (WHERE reason = 'drop') is blocked too, and
that cost is accepted.
"""

from __future__ import annotations

import re

ALLOWED_SCHEMAS = {"healthcare_dev.gold", "healthcare_dev.metrics"}
CATALOGS = {"healthcare_dev", "healthcare", "system", "samples", "workspace", "main"}

WRITE_WORDS = re.compile(
    r"\b(drop|delete|insert|update|merge|alter|create|grant|revoke|truncate|copy"
    r"|optimize|vacuum|refresh|call)\b", re.I)
FUNCTIONS = re.compile(r"\b(ai_\w+|read_files|http_request|secret|reflect|java_method)\s*\(",
                       re.I)
# Functions whose syntax contains FROM without naming a table.
FROM_INSIDE = re.compile(r"\b(extract|trim|substring|overlay|position)\s*\([^()]*\)", re.I)
TABLE = re.compile(r"\b(?:from|join)\s+([`\w.]+)", re.I)
CTE = re.compile(r"(?:\bwith|,)\s*(\w+)\s+as\s*\(", re.I)
THREE_PART = re.compile(r"\b(\w+)\.(\w+)\.(\w+)\b")


def problem(sql: str) -> str | None:
    text = sql.strip().rstrip(";").strip()
    if ";" in text:
        return "more than one statement"
    if not re.match(r"(select|with)\b", text, re.I):
        return "not a SELECT"
    if found := WRITE_WORDS.search(text):
        return f"blocked word: {found.group(1).lower()}"
    if found := FUNCTIONS.search(text):
        return f"blocked function: {found.group(1).lower()}"
    ctes = {name.lower() for name in CTE.findall(text)}
    for ref in TABLE.findall(FROM_INSIDE.sub("", text)):
        name = ref.replace("`", "").lower()
        if name in ctes:
            continue
        if name.count(".") != 2 or name.rsplit(".", 1)[0] not in ALLOWED_SCHEMAS:
            return f"table outside gold and metrics: {name}"
    # Catches tables a FROM/JOIN scan misses, such as a comma join.
    for catalog, schema, _ in THREE_PART.findall(text):
        if (catalog.lower() in CATALOGS
                and f"{catalog}.{schema}".lower() not in ALLOWED_SCHEMAS):
            return f"table outside gold and metrics: {catalog}.{schema}"
    return None
