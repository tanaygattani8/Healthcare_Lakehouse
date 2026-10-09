import pytest

from scripts.readmission_story import (
    Side,
    complete_suppression,
    level_row,
    separates,
    shortlist,
    verdict,
    wilson,
)


def test_wilson_matches_the_textbook():
    low, high = wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4)
    assert high == pytest.approx(0.7634, abs=1e-4)


def test_wilson_stays_inside_0_and_1():
    # Where p ± 1.96·se would go below 0 or above 1.
    assert wilson(0, 10)[0] == pytest.approx(0.0, abs=1e-12)
    assert wilson(10, 10)[1] == pytest.approx(1.0, abs=1e-12)


def test_wilson_for_the_whole_table():
    low, high = wilson(140, 10724)                    # D68's table
    assert (round(low, 4), round(high, 4)) == (0.0111, 0.0154)


REST = Side(stays=1046, readmitted=161, readmitted_patients=140)


def test_a_clear_difference_separates():
    assert separates(Side(100, 40, 30), REST)          # 40% vs 15%


def test_overlapping_intervals_do_not_separate():
    assert not separates(Side(100, 20, 15), Side(1000, 150, 120))


def test_under_30_stays_on_either_side_never_separates():
    assert not separates(Side(29, 20, 15), REST)
    assert not separates(REST, Side(29, 20, 15))


def test_the_higher_side_needs_10_readmitted_patients():
    # 40 readmissions from 9 people: a few frequent returners, not a signal.
    assert not separates(Side(100, 40, 9), REST)
    # And when the higher side is the rest.
    assert not separates(Side(500, 20, 18), Side(600, 150, 9))


def test_shortlist_keeps_only_signals_known_at_discharge():
    rows = [("prior_stays_12m_band", True), ("prior_stays_12m_band", False),
            ("post_followup_7d", True), ("admit_period", True), ("gender", False)]
    assert shortlist(rows) == ["prior_stays_12m_band"]


def test_go_needs_two_signals():
    assert verdict([]) == "NO-GO"
    assert verdict(["gender"]) == "NO-GO"
    assert verdict(["gender", "has_diabetes"]) == "GO"


def test_a_published_row_has_rates_and_intervals():
    row = level_row("prior_stays_12m_band", "2+", Side(100, 40, 30), REST)
    assert row["chapter"] == 3 and row["at_discharge"] and row["separates"]
    assert row["rate"] == 0.4 and row["low"] < 0.4 < row["high"]
    assert row["rest_stays"] == 1046
    assert "readmitted_patients" not in row           # used, never published


def test_a_small_cell_loses_its_counts_but_not_its_decision():
    row = level_row("gender", "M", Side(10, 3, 3), REST)
    assert row["suppressed"] and row["separates"] is False
    assert "index_stays" not in row and "rate" not in row


def test_follow_up_is_shown_but_never_at_discharge():
    row = level_row("post_followup_7d", "true", Side(100, 10, 10), REST)
    assert row["at_discharge"] is False


# Made-up counts: real hidden ones would undo their suppression.

def test_few_readmissions_are_hidden_even_in_a_big_level():
    row = level_row("age_band", "80+", Side(400, 6, 6), Side(9000, 150, 130))
    assert row["suppressed"] and "rate" not in row and "readmitted" not in row


def test_few_readmissions_in_the_rest_hide_the_level_too():
    # 150 = 156 - 6: publishing the level would give the rest's 6 back.
    row = level_row("is_planned", "false", Side(7000, 150, 130), Side(2400, 6, 6))
    assert row["suppressed"]


def test_zero_readmissions_is_published():
    row = level_row("age_band", "0-17", Side(800, 0, 0), Side(8600, 156, 136))
    assert not row["suppressed"] and row["readmitted"] == 0


TOTAL = Side(9400, 156, 136)


def _rows(signal, levels, total=TOTAL):
    return [level_row(signal, level, Side(stays, readmitted, 10),
                      Side(total.stays - stays, total.readmitted - readmitted, 100))
            for level, stays, readmitted in levels]


def test_a_lone_hidden_level_takes_a_second_one_with_it():
    rows = complete_suppression(_rows("prior_stays_12m_band",
                                      [("0", 8000, 120), ("1", 1300, 31), ("2+", 100, 5)]))
    assert [r["suppressed"] for r in rows] == [False, True, True]
    assert "readmitted" not in rows[1]


def test_the_complement_prefers_a_level_with_readmissions():
    # Hiding 0-17 (no readmissions) would leave 6 to subtraction, so 65-79 goes.
    rows = complete_suppression(_rows(
        "age_band", [("0-17", 800, 0), ("45-64", 4000, 120), ("65-79", 3000, 60), ("80+", 1600, 6)],
        total=Side(9400, 186, 160)))
    assert {r["level"]: r["suppressed"] for r in rows} == {
        "0-17": False, "45-64": False, "65-79": True, "80+": True}


def test_hidden_levels_that_sum_to_1_to_10_take_the_other_level_with_them():
    # The audit's shape (D79): hidden reasons left 10 readmissions; "other" goes next.
    rows = complete_suppression(_rows("admit_reason_group", [
        ("other", 4238, 71), ("cabg", 606, 59), ("a", 2000, 4), ("b", 1900, 3),
        ("c", 1000, 2), ("d", 980, 1)], total=Side(10724, 140, 127)))
    assert {r["level"]: r["suppressed"] for r in rows} == {
        "other": True, "cabg": False, "a": True, "b": True, "c": True, "d": True}


def test_hidden_levels_holding_11_or_more_need_no_more():
    # 80+ and 18-44 hidden together hold 1,600 stays and 13 readmissions.
    rows = _rows("age_band", [("0-17", 800, 0), ("45-64", 4000, 120), ("65-79", 3000, 45),
                              ("80+", 1595, 8), ("18-44", 5, 5)], total=Side(9400, 178, 160))
    assert [r["suppressed"] for r in complete_suppression(rows)] == [
        False, False, False, True, True]


def test_two_hidden_levels_need_no_more():
    rows = _rows("is_planned", [("false", 7000, 150), ("true", 2400, 6)])
    assert all(r["suppressed"] for r in rows)
    assert complete_suppression(rows) == rows


def test_a_post_or_outcome_signal_is_never_shortlisted():
    assert shortlist([("post_anything", True), ("outcome_x", True), ("gender", True)]) == ["gender"]
