"""Every SQL statement parses (or its query body does), and every file is UTF-8 (D81)."""
import logging
import re
from pathlib import Path

import pytest
import sqlglot
import yaml
from sqlglot import exp
from sqlglot.errors import ErrorLevel

from scripts.run_sql import _statements

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(p for folder in ("sql", "pipelines", "setup")
               for p in (ROOT / folder).rglob("*.sql"))
# The query a CREATE ... AS wraps, from its SELECT or WITH to the end.
BODY = re.compile(r"\bAS\s*\(?\s*(SELECT|WITH)\b", re.IGNORECASE)
METRIC_VIEW = re.compile(r"LANGUAGE\s+YAML\s+AS\s+\$\$(.*)\$\$", re.IGNORECASE | re.DOTALL)
# sqlglot's fallback to a generic Command logs a warning per statement.
logging.getLogger("sqlglot").setLevel(logging.ERROR)


def code(statement: str) -> str:
    """The statement without comments, and with the pipeline's catalog filled in."""
    lines = [line.split("--")[0] for line in statement.splitlines()]
    return "\n".join(lines).replace("${catalog}", "healthcare_dev").strip().rstrip(";")


def parse(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, read="databricks", error_level=ErrorLevel.RAISE)


def metric_view_problem(body: str) -> str | None:
    """A metric view's YAML must load, and its filter, joins and every expr parse."""
    try:
        view = yaml.safe_load(body)
        for item in view.get("dimensions", []) + view.get("measures", []):
            parse(f"SELECT {item['expr']} FROM t")
        for join in view.get("joins", []):
            # YAML 1.1 reads the key `on` as True.
            parse(f"SELECT 1 FROM a JOIN b ON {join.get('on', join.get(True))}")
        if "filter" in view:
            parse(f"SELECT 1 FROM t WHERE {view['filter']}")
    except (yaml.YAMLError, sqlglot.errors.SqlglotError) as error:
        return f"metric view: {str(error).splitlines()[0]}"
    return None


def problem(statement: str) -> str | None:
    """Why this statement fails the check, or None."""
    sql = code(statement)
    if view := METRIC_VIEW.search(sql):
        return metric_view_problem(view.group(1))
    if "LANGUAGE PYTHON" in sql.upper():
        return None   # a Python body, which sqlglot cannot tokenise
    try:
        if not isinstance(parse(sql), exp.Command):
            return None
    except sqlglot.errors.SqlglotError as error:
        failed = str(error).splitlines()[0]
    else:
        failed = None   # DDL sqlglot does not model; only its query can be checked
    body = BODY.search(sql)
    if body is None:
        return failed
    try:
        parse(sql[body.start(1):])
        return None
    except sqlglot.errors.SqlglotError as error:
        return f"query body: {str(error).splitlines()[0]}"


def test_the_check_catches_a_broken_query():
    assert problem("SELECT a FROM t") is None
    assert problem("SELECT a FROM t WHERE (a = 1") is not None
    assert problem("CREATE OR REFRESH MATERIALIZED VIEW v (CONSTRAINT c EXPECT (x > 0) "
                   "ON VIOLATION FAIL UPDATE) AS SELECT a FROM t") is None
    assert problem("CREATE OR REFRESH MATERIALIZED VIEW v (CONSTRAINT c EXPECT (x > 0) "
                   "ON VIOLATION FAIL UPDATE) AS SELECT a FROM t WHERE (") is not None
    view = "CREATE VIEW v WITH METRICS LANGUAGE YAML AS $$\nsource: t\nmeasures:\n  - name: m\n"
    assert problem(view + "    expr: count(*)\n$$") is None
    assert problem(view + "    expr: count_if(x\n$$") is not None


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_statement_parses(path):
    text = path.read_text(encoding="utf-8")   # raises on a file that is not UTF-8
    bad = [(problem(s), code(s)[:80]) for s in _statements(text)]
    bad = [b for b in bad if b[0]]
    assert not bad, bad
