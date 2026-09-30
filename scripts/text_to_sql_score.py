"""Mark one text-to-SQL answer: a verdict per contestant per question.

Execution accuracy (spec §5): the contestant's result must equal the answer
key's, however different the SQL. Pure functions; nothing here touches
Databricks, so every rule is tested on the laptop.
"""

from __future__ import annotations

import math
from decimal import Decimal
from itertools import product

REFUSE = "REFUSE"
MAX_ROWS = 10_000
TOLERANCE = 0.005            # half a unit in the 2nd decimal
MAX_ASSIGNMENTS = 1_000      # ponytail: capped for many identical columns; upgrade if exhausted

VERDICTS = ("correct", "wrong_result", "sql_error", "blocked", "too_many_rows",
            "answered_unanswerable", "wrongly_refused", "error")


def is_refusal(reply: str) -> bool:
    return reply.strip().strip(".").upper() == REFUSE


def _normal(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | Decimal):
        v = float(value)
        if math.isnan(v):
            return "nan"  # sentinel: NaN equals NaN
        return v
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

    # Find candidate actual columns for each expected column.
    # A column j is a candidate for expected column i if their values
    # (as unordered multisets) match within tolerance.
    candidates = []
    for exp_col in range(width):
        exp_values = [tuple([row[exp_col]]) for row in expected]
        col_candidates = []
        for act_col in range(have):
            act_values = [tuple([row[act_col]]) for row in actual]
            # Check if these single-column lists match as unordered multisets
            if _rows_equal(exp_values, act_values, ordered=False):
                col_candidates.append(act_col)
        if not col_candidates:
            return False
        candidates.append(col_candidates)

    # Search for valid assignments: one actual column per expected column,
    # with no actual column used twice.
    assignments_tried = 0
    for assignment in product(*candidates):
        if len(set(assignment)) != len(assignment):
            # This assignment uses an actual column twice, skip it
            continue
        assignments_tried += 1
        if assignments_tried > MAX_ASSIGNMENTS:
            # ponytail: many identical columns multiply choices; upgrade if needed
            return False
        # Project actual rows to this assignment
        projected = [tuple(row[c] for c in assignment) for row in actual]
        if _rows_equal(expected, projected, ordered):
            return True

    return False


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
