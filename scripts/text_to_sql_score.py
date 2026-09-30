"""Mark one text-to-SQL answer: a verdict per contestant per question.

Execution accuracy (spec §5): the contestant's result must equal the answer
key's, however different the SQL. Pure functions; nothing here touches
Databricks, so every rule is tested on the laptop.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import permutations

REFUSE = "REFUSE"
MAX_ROWS = 10_000
TOLERANCE = 0.005            # half a unit in the 2nd decimal
# ponytail: columns are matched by trying orders; 8 columns choose 4 is
# 1,680 tries. Wider answers are compared in their own order only.
MAX_COLUMNS = 8

VERDICTS = ("correct", "wrong_result", "sql_error", "blocked", "too_many_rows",
            "answered_unanswerable", "wrongly_refused", "error")


def is_refusal(reply: str) -> bool:
    return reply.strip().strip(".").upper() == REFUSE


def _normal(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= TOLERANCE
    return a == b


def _sort_key(row: tuple) -> tuple:
    # Mixed types and NULLs must sort without error. Numbers sort by their
    # 2-decimal value, so values within the tolerance land side by side.
    # ponytail: two numbers straddling a rounding edge can sort apart; widen
    # the key if that ever shows up as a false wrong_result.
    return tuple((0, "") if v is None
                 else (1, round(v, 2)) if isinstance(v, float) and not isinstance(v, bool)
                 else (2, str(v)) for v in row)


def _rows_equal(expected: list[tuple], actual: list[tuple], ordered: bool) -> bool:
    if len(expected) != len(actual):
        return False
    if not ordered:
        expected, actual = sorted(expected, key=_sort_key), sorted(actual, key=_sort_key)
    return all(all(_same(e, a) for e, a in zip(e_row, a_row, strict=True))
               for e_row, a_row in zip(expected, actual, strict=True))


def results_match(expected: list[tuple], actual: list[tuple], ordered: bool = False) -> bool:
    expected = [tuple(_normal(v) for v in row) for row in expected]
    actual = [tuple(_normal(v) for v in row) for row in actual]
    if not expected:
        return not actual
    if not actual:
        return False
    width, have = len(expected[0]), len(actual[0])
    if have < width:
        return False
    orders = [tuple(range(width))] if have > MAX_COLUMNS else permutations(range(have), width)
    return any(_rows_equal(expected, [tuple(row[c] for c in cols) for row in actual], ordered)
               for cols in orders)


def decide(*, answerable: bool, reply: str | None, gate_problem: str | None = None,
           run_error: str | None = None, expected: list[tuple] | None = None,
           actual: list[tuple] | None = None, ordered: bool = False) -> str:
    """Exactly one verdict. The order of the checks is the order of the flow."""
    if reply is None:
        return "error"
    if is_refusal(reply):
        return "wrongly_refused" if answerable else "correct"
    if not answerable:
        return "answered_unanswerable"
    if gate_problem:
        return "blocked"
    if run_error:
        return "sql_error"
    if len(actual) > MAX_ROWS:
        return "too_many_rows"
    return "correct" if results_match(expected, actual, ordered) else "wrong_result"
