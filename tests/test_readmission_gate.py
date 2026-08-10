from pathlib import Path

import duckdb
import pytest

from scripts.readmission_gate import compute_gate, verdict

ENC_HEADER = "Id,START,STOP,PATIENT,ENCOUNTERCLASS\n"
PAT_HEADER = "Id,DEATHDATE\n"


@pytest.fixture
def con():
    return duckdb.connect()


def write(tmp_path: Path, encounters: str, patients: str) -> tuple[Path, Path]:
    enc = tmp_path / "encounters.csv"
    pat = tmp_path / "patients.csv"
    enc.write_text(ENC_HEADER + encounters)
    pat.write_text(PAT_HEADER + patients)
    return enc, pat


def test_readmission_within_window_is_flagged(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2020-01-20T00:00:00Z,2020-01-25T00:00:00Z,p1,inpatient\n"
        "e3,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p1,inpatient\n",
        "p1,\n",
    )

    result = compute_gate(con, enc, pat)

    assert result["readmissions"] == 1


def test_gap_beyond_window_is_not_a_readmission(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2020-03-01T00:00:00Z,2020-03-05T00:00:00Z,p1,inpatient\n"
        "e3,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p1,inpatient\n",
        "p1,\n",
    )

    assert compute_gate(con, enc, pat)["readmissions"] == 0


def test_exactly_at_window_boundary_counts(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2020-02-04T00:00:00Z,2020-02-06T00:00:00Z,p1,inpatient\n"
        "e3,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p1,inpatient\n",
        "p1,\n",
    )

    # 2020-01-05 discharge -> 2020-02-04 admission is exactly 30 days
    assert compute_gate(con, enc, pat)["readmissions"] == 1


def test_same_day_reentry_is_a_transfer_not_a_readmission(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2020-01-05T00:00:00Z,2020-01-08T00:00:00Z,p1,inpatient\n"
        "e3,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p1,inpatient\n",
        "p1,\n",
    )

    assert compute_gate(con, enc, pat)["readmissions"] == 0


def test_non_inpatient_encounters_are_ignored(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2020-01-10T00:00:00Z,2020-01-10T00:00:00Z,p1,ambulatory\n"
        "e3,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p1,inpatient\n",
        "p1,\n",
    )

    result = compute_gate(con, enc, pat)

    assert result["inpatient_encounters"] == 2
    assert result["readmissions"] == 0


def test_death_at_index_excludes_the_admission(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p2,inpatient\n",
        "p1,2020-01-05\np2,\n",
    )

    result = compute_gate(con, enc, pat)

    assert result["excluded_death"] == 1


def test_insufficient_follow_up_is_excluded(tmp_path, con):
    # e2 discharges 10 days before the end of the data — it cannot be observed
    # for a full 30 days, so it must not be counted as an index admission.
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2021-05-20T00:00:00Z,2021-05-22T00:00:00Z,p2,inpatient\n"
        "e3,2021-06-01T00:00:00Z,2021-06-01T00:00:00Z,p3,inpatient\n",
        "p1,\np2,\np3,\n",
    )

    result = compute_gate(con, enc, pat)

    assert result["excluded_short_followup"] == 2  # e2 and e3


def test_base_rate_is_readmissions_over_index_admissions(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-05T00:00:00Z,p1,inpatient\n"
        "e2,2020-01-20T00:00:00Z,2020-01-25T00:00:00Z,p1,inpatient\n"
        "e3,2020-02-01T00:00:00Z,2020-02-03T00:00:00Z,p2,inpatient\n"
        "e4,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p3,inpatient\n",
        "p1,\np2,\np3,\n",
    )

    result = compute_gate(con, enc, pat)

    assert result["index_admissions"] == 3  # e1, e2, e3 — e4 lacks follow-up
    assert result["readmissions"] == 1
    assert result["base_rate"] == pytest.approx(1 / 3)


def test_empty_index_set_gives_zero_base_rate_not_division_error(tmp_path, con):
    enc, pat = write(
        tmp_path,
        "e1,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p1,inpatient\n",
        "p1,\n",
    )

    assert compute_gate(con, enc, pat)["base_rate"] == 0.0


def test_overlapping_stay_blocks_the_lookahead(tmp_path, con):
    """Pins the known ceiling in NEXT_ADMITTED_SQL rather than leaving it implicit.

    e2 is nested inside e1's stay. LEAD orders by admission, so e1's lookahead
    lands on e2 (which starts *before* e1 discharges) and never reaches e3,
    15 days after e1's discharge. e3 is counted once — against e2, not e1.

    Merging overlapping stays into one index admission is the correct fix and
    belongs in phase 4's gold layer, not in a gate. If this test starts failing
    with 2, someone changed the lookahead to min-after-discharge, which
    double-attributes one readmission to two index stays. On the real dev-tier
    dataset the two approaches differ by 3.4 points of base rate.
    """
    enc, pat = write(
        tmp_path,
        "e1,2020-01-01T00:00:00Z,2020-01-10T00:00:00Z,p1,inpatient\n"
        "e2,2020-01-05T00:00:00Z,2020-01-08T00:00:00Z,p1,inpatient\n"
        "e3,2020-01-25T00:00:00Z,2020-01-27T00:00:00Z,p1,inpatient\n"
        "e4,2021-06-01T00:00:00Z,2021-06-03T00:00:00Z,p2,inpatient\n",
        "p1,\np2,\n",
    )

    assert compute_gate(con, enc, pat)["readmissions"] == 1


def test_verdict_covers_every_branch():
    """verdict() is the function that produces the actual decision, and it is
    pure branching — exactly the shape that passes review untested and then
    ships the wrong call."""
    assert "PIVOT" in verdict({"index_admissions": 499, "base_rate": 0.15})
    assert "PIVOT" in verdict({"index_admissions": 5000, "base_rate": 0.005})
    assert "PIVOT" in verdict({"index_admissions": 5000, "base_rate": 0.61})
    assert "PROCEED" in verdict({"index_admissions": 5000, "base_rate": 0.15})
    # Boundaries belong to PROCEED, not PIVOT.
    assert "PROCEED" in verdict({"index_admissions": 500, "base_rate": 0.01})
    assert "PROCEED" in verdict({"index_admissions": 500, "base_rate": 0.60})
