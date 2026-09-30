"""May this generated SQL run? Checked before every contestant's statement.

The warehouse runs as the only principal, who owns everything, so a
generated DROP TABLE would execute (spec §4). This is a parser allow-list:
sqlglot parses the statement (Databricks dialect) and every table node in the
tree must be a CTE or sit in healthcare_dev.gold / healthcare_dev.metrics.
Anything that does not parse is blocked (fail closed).

The spec's keyword scan on the raw text remains as belt and braces, so
harmless text containing a blocked word (WHERE reason = 'update') is blocked
too. That cost is accepted.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

ALLOWED_SCHEMAS = {"healthcare_dev.gold", "healthcare_dev.metrics"}

WRITE_WORDS = re.compile(
    r"\b(drop|delete|insert|update|merge|alter|create|grant|revoke|truncate|copy)\b",
    re.I)
BLOCKED_FUNCTIONS = {"read_files", "http_request", "secret", "reflect", "java_method",
                     "table_changes", "read_kafka", "vector_search", "identifier"}


def _function_names(node: exp.Func) -> set[str]:
    if isinstance(node, exp.Anonymous):
        return {node.name.lower()}
    return {node.sql_name().lower(), node.key.lower()}


def problem(sql: str) -> str | None:
    if found := WRITE_WORDS.search(sql):
        return f"blocked word: {found.group(1).lower()}"
    try:
        parsed = sqlglot.parse(sql, read="databricks")
    except Exception:
        return "does not parse"
    # A trailing ';' or comment can yield None or a bare Semicolon node.
    statements = [s for s in parsed if s is not None and not isinstance(s, exp.Semicolon)]
    if len(statements) != 1:
        return "more than one statement"
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        return "not a SELECT"

    ctes = {cte.alias.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            return f"blocked table expression: {table.sql('databricks')}"
        if not table.catalog and not table.db and table.name.lower() in ctes:
            continue
        if f"{table.catalog}.{table.db}".lower() not in ALLOWED_SCHEMAS:
            return f"table outside gold and metrics: {table.sql('databricks')}"

    for func in tree.find_all(exp.Func):
        for name in _function_names(func):
            if name.startswith("ai_") or name in BLOCKED_FUNCTIONS:
                return f"blocked function: {name}"
    return None
