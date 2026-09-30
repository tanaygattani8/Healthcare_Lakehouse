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
# sqlglot types most functions; one it does not recognise is blocked unless listed.
ALLOWED_UNKNOWN_FUNCTIONS = {"measure", "make_date", "make_timestamp", "date_part"}
# Dangerous names that sqlglot may type (secret) or that arrive via try_ variants.
BLOCKED_FUNCTIONS = re.compile(
    r"(try_)?(secret|reflect|java_method)|ai_.*|read_files|http_request|table_changes"
    r"|read_kafka|vector_search|identifier|list_secrets|event_log|cloud_files_state"
    r"|remote_query|read_state|python_exec|call_function|table")
LATERAL_FUNCTIONS = {"explode", "explode_outer", "posexplode", "posexplode_outer",
                     "inline", "inline_outer", "stack"}


def _names(node: exp.Func) -> set[str]:
    if isinstance(node, exp.Anonymous):
        return {node.name.lower()}
    return {node.sql_name().lower(), node.key.lower()}


def _function_problem(tree: exp.Expression) -> str | None:
    # Unqualified names are safe only because the harness runs
    # USE healthcare_dev.metrics first.
    for dot in tree.find_all(exp.Dot):
        if isinstance(dot.expression, exp.Func):
            return f"blocked function: {dot.sql('databricks')}"
    for func in tree.find_all(exp.Func):
        names = _names(func)
        if isinstance(func, exp.Anonymous) and not names <= ALLOWED_UNKNOWN_FUNCTIONS:
            return f"blocked function: {func.name.lower()}"
        for name in names:
            if BLOCKED_FUNCTIONS.fullmatch(name):
                return f"blocked function: {name}"
    for lateral in tree.find_all(exp.Lateral):
        if not isinstance(lateral.this, exp.Query) and not (
                isinstance(lateral.this, exp.Func) and _names(lateral.this) & LATERAL_FUNCTIONS):
            return f"blocked lateral: {lateral.sql('databricks')}"
    return None


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
    return _function_problem(tree)
