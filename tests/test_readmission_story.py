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
            ("post_followup_7d", True), ("admit_year", True), ("gender", False)]
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


def test_few_readmissions_are_hidden_even_in_a_big_level():
    row = level_row("age_band", "80+", Side(308, 7, 7), Side(10416, 166, 151))
    assert row["suppressed"] and "rate" not in row and "readmitted" not in row


def test_few_readmissions_in_the_rest_hide_the_level_too():
    # 166 = 173 - 7: publishing the level would give the rest's 7 back.
    row = level_row("is_planned", "false", Side(8409, 166, 151), Side(2315, 7, 7))
    assert row["suppressed"]


def test_zero_readmissions_is_published():
    row = level_row("age_band", "0-17", Side(739, 0, 0), Side(9985, 173, 158))
    assert not row["suppressed"] and row["readmitted"] == 0


def test_a_lone_hidden_level_takes_a_second_one_with_it():
    total = Side(10724, 173, 158)

    def row(level, stays, readmitted):
        rest = Side(total.stays - stays, total.readmitted - readmitted, 100)
        return level_row("prior_stays_12m_band", level, Side(stays, readmitted, 10), rest)

    rows = complete_suppression([row("0", 9704, 139), row("1", 924, 30), row("2+", 96, 4)])
    assert [r["suppressed"] for r in rows] == [False, True, True]
    assert "readmitted" not in rows[1]


def test_two_hidden_levels_need_no_more():
    rows = [level_row("is_planned", level, side, rest) for level, side, rest in
            [("false", Side(8409, 166, 151), Side(2315, 7, 7)),
             ("true", Side(2315, 7, 7), Side(8409, 166, 151))]]
    assert complete_suppression(rows) == rows
