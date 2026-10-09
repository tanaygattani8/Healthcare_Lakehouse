import time
from decimal import Decimal

import pytest

from scripts.text_to_sql_score import decide, is_refusal, results_match


def test_row_order_ignored_unless_asked():
    expected, actual = [("a", 1), ("b", 2)], [("b", 2), ("a", 1)]
    assert results_match(expected, actual)
    assert not results_match(expected, actual, ordered=True)


def test_columns_matched_by_value_not_position():
    assert results_match([("inpatient", 5)], [(5, "inpatient")])


def test_extra_columns_are_allowed():
    assert results_match([(17.54,)], [(201, 1146, 17.54)])


def test_missing_column_is_wrong():
    assert not results_match([(201, 1146)], [(201,)])


def test_decimal_and_double_compare_as_numbers():
    assert results_match([(Decimal("17.54"),)], [(17.54,)])
    assert results_match([(17.54,)], [(17.543,)])


def test_a_fraction_is_not_a_percent():
    assert not results_match([(17.54,)], [(0.1754,)])


def test_text_is_trimmed_and_case_folded_and_nulls_are_equal():
    assert results_match([("Inpatient", None)], [(" inpatient", None)])


def test_row_count_must_match():
    assert not results_match([(1,)], [(1,), (1,)])


def test_empty_answers():
    assert results_match([], [])
    assert not results_match([], [(0,)])


def test_refusal_is_recognised_loosely():
    assert is_refusal("REFUSE") and is_refusal(" refuse. ")
    assert not is_refusal("SELECT 'REFUSE'")


@pytest.mark.parametrize("kwargs, verdict", [
    (dict(answerable=True, reply=None), "error"),
    (dict(answerable=True, reply="REFUSE"), "wrongly_refused"),
    (dict(answerable=False, reply="refuse."), "correct"),
    (dict(answerable=False, reply="SELECT 1"), "answered_unanswerable"),
    (dict(answerable=True, reply="DROP TABLE x", gate_problem="not a SELECT"), "blocked"),
    (dict(answerable=True, reply="SELECT x", run_error="UNRESOLVED_COLUMN"), "sql_error"),
    (dict(answerable=True, reply="SELECT 1", expected=[(1,)], actual=[(1,)] * 10_001),
     "too_many_rows"),
    (dict(answerable=True, reply="SELECT 1", expected=[(1,)], actual=[(2,)]), "wrong_result"),
    (dict(answerable=True, reply="SELECT 1", expected=[(1,)], actual=[(1,)]), "correct"),
])
def test_every_verdict(kwargs, verdict):
    assert decide(**kwargs) == verdict


def test_answer_column_found_in_a_wide_result():
    assert results_match([(5,)], [(8, 7, 6, 5, 4, 3, 2, 1, 0)])


def test_wide_result_scoring_grows_linearly_not_quadratically():
    # A ratio of two timed sizes doesn't flake: 10x rows is ~10x linear, ~100x quadratic.
    expected = [(i, i * 2, i * 3, i * 4) for i in range(10_000)]
    actual = [(0, i * 4, 1, i, 2, i * 3, 3, i * 2) for i in range(10_000)]

    def timed(n: int) -> float:
        start = time.perf_counter()
        assert results_match(expected[:n], actual[:n]) is True
        return time.perf_counter() - start

    small, large = timed(1_000), timed(10_000)
    assert large < 30 * small, f"10,000 rows {large:.2f}s vs 1,000 rows {small:.2f}s"


def test_nan_equals_nan():
    assert results_match([(float("nan"),)], [(float("nan"),)])
