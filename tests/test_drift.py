import numpy as np
import pandas as pd

from scripts import drift


def test_the_same_distribution_is_stable():
    rng = np.random.default_rng(0)
    a, b = rng.normal(50, 15, 3000), rng.normal(50, 15, 3000)
    assert drift.status(drift.psi(a, b, "number")) == "stable"


def test_age_moved_up_15_years_is_shifted():
    a = np.random.default_rng(0).normal(50, 15, 3000)
    assert drift.status(drift.psi(a, a + 15, "number")) == "shifted"


def test_a_category_never_seen_in_training_is_shifted_and_does_not_crash():
    train = ["M", "F"] * 500
    prod = ["M", "F", "COVID-19"] * 300
    assert drift.status(drift.psi(train, prod, "category")) == "shifted"


def test_an_empty_bin_gives_a_finite_psi():
    value = drift.psi(np.arange(100.0), np.zeros(50), "number")
    assert np.isfinite(value) and value > drift.SHIFTED


def test_missing_values_are_their_own_bin():
    a = pd.Series([1.0, 2.0, np.nan] * 100)
    assert drift.psi(a, a, "number") == 0
    assert drift.status(drift.psi(a, pd.Series([1.0, 2.0] * 150), "number")) == "shifted"


def test_status_thresholds():
    assert [drift.status(v) for v in (0.05, 0.1, 0.25, 0.26)] == \
        ["stable", "watch", "watch", "shifted"]


def test_drift_report_one_row_per_feature():
    train = pd.DataFrame({"age": np.arange(100.0), "gender": ["M", "F"] * 50})
    rows = drift.drift_report(train, train.assign(age=train["age"] + 60),
                              {"age": "number", "gender": "category"})
    assert [(r["feature"], r["status"]) for r in rows] == [("age", "shifted"),
                                                          ("gender", "stable")]


def test_interval_status():
    assert drift.interval_status(0.25, 25, 100) == "stable"
    assert drift.interval_status(0.25, 60, 100) == "shifted"


def test_a_count_that_is_mostly_zero_still_shows_its_shift():
    # 95% zeros collapse the quantile edges to [0, 1]; with right-closed bins
    # 0, 1 and 2 shared a bin and this read PSI 0.
    train = [0] * 950 + [1] * 40 + [2] * 10
    prod = [0] * 500 + [1] * 300 + [3] * 200
    assert drift.status(drift.psi(train, prod, "number")) == "shifted"
    assert drift.psi(train, train, "number") == 0


def test_a_true_false_feature_is_judged_by_its_rate_not_psi():
    # 22% -> 35%: PSI is under 0.1 ("stable"), but the rate moved 13 points.
    train = pd.DataFrame({"heart": [1] * 220 + [0] * 780})
    big = pd.DataFrame({"heart": [1] * 354 + [0] * 646})
    assert drift.psi(train["heart"], big["heart"], "category") < drift.WATCH
    assert drift.drift_report(train, big, {"heart": "flag"})[0]["status"] == "shifted"
    # 22% -> 25%: outside the 95% interval, but under 5 points.
    small = pd.DataFrame({"heart": [1] * 250 + [0] * 750})
    assert drift.drift_report(train, small, {"heart": "flag"})[0]["status"] == "watch"
    assert drift.drift_report(train, train, {"heart": "flag"})[0]["status"] == "stable"
