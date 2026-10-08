"""Made-up rows only (CLAUDE.md: never a real small count in a fixture)."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone

from scripts import readmission_model as rm
from scripts import retrain as rt
from tests.test_readmission_model import _days, _signals

D = dt.date


def test_windows_are_the_two_years_before_as_of():
    assert rt.windows(D(2023, 1, 1)) == {"check": (D(2022, 1, 1), D(2023, 1, 1)),
                                         "cutoff": (D(2021, 1, 1), D(2022, 1, 1))}
    # The live run's as_of is mid-year.
    assert rt.windows(D(2026, 7, 15))["check"] == (D(2025, 7, 15), D(2026, 7, 15))


def test_admitted_takes_the_start_day_and_not_the_end_day():
    df = _days(("2021-12-31", "2022-01-02"), ("2022-01-01", "2022-01-03"),
               ("2022-12-31", "2023-01-01"), ("2023-01-01", "2023-01-02"))
    assert list(df[rt.admitted(df, D(2022, 1, 1), D(2023, 1, 1))]["stay_no"]) == [1, 2]


def test_a_label_is_known_30_days_after_discharge():
    assert rt.labels_known_by(D(2021, 1, 1)) == D(2020, 12, 2)
    df = _days(("2020-11-20", "2020-12-02"), ("2020-11-21", "2020-12-03"))
    assert list(rt.labelled(df, D(2021, 1, 1))) == [True, False]


def test_v2s_training_tags_select_exactly_phase_6s_training_stays():
    df = _days(("2019-11-20", "2019-12-01"), ("2019-11-25", "2019-12-02"),
               ("2019-12-31", "2020-01-02"), ("2020-01-01", "2020-01-03"))
    train, _, _ = rm.split(df)
    picked = df[rt.trained_on(df, rm.PROD_FROM, rm.TRAIN_UNTIL, rm.TRAIN_FROM)]
    assert list(picked["stay_no"]) == list(train["stay_no"]) == [0]


def test_a_lower_bound_leaves_out_older_stays_and_none_means_no_bound():
    df = _days(("1999-12-31", "2000-01-02"), ("2000-01-01", "2000-01-03"))
    assert list(rt.trained_on(df, rm.PROD_FROM, rm.TRAIN_UNTIL, "2000-01-01")) == [False, True]
    assert list(rt.trained_on(df, rm.PROD_FROM, rm.TRAIN_UNTIL)) == [True, True]
    assert rt.TRAIN_YEARS == 20


def test_the_budget_ignores_production_stays():
    df = _signals(n=600)
    before = rt.budget(df)
    production = pd.to_datetime(df["admit_day"]) >= pd.Timestamp(rm.PROD_FROM)
    df.loc[production, "has_cardiovascular_disease"] = True
    assert rt.budget(df) == before
    assert 0 < before < 1


def test_settings_read_logged_strings_back_into_the_grids_types():
    assert rt.settings({"kind": "boosting", "max_depth": "3", "learning_rate": "0.05",
                        "k": "868"}) == ("boosting", {"max_depth": 3, "learning_rate": 0.05})
    assert rt.settings({"kind": "logistic", "C": "1"}) == ("logistic", {"C": 1.0})


def test_scoring_starts_at_production_or_after_the_models_training():
    assert rt.scored_from({}) == rm.PROD_FROM
    assert rt.scored_from({"train_admit_before": "2023-01-01"}) == "2023-01-01"
    assert rt.scored_from({"train_admit_before": "2019-06-01"}) == rm.PROD_FROM


def test_window_scores_are_plain_on_unseen_stays_and_out_of_fold_on_seen_ones():
    df = _signals(n=600)
    trained, window = df.iloc[:400], df.iloc[300:500]  # 100 seen, then 100 unseen
    fresh = rm.build_pipeline("logistic", {"C": 1}, "all")
    model = clone(fresh).fit(rm.build_features(trained, "all"), trained[rm.TARGET].astype(int))
    got = rt.window_scores(model, fresh, trained, window)
    plain = model.predict_proba(rm.build_features(window, "all"))[:, 1]
    oof = rm.oof_scores(fresh, trained, "all")
    assert np.allclose(got[100:], plain[100:])
    assert np.allclose(got[:100], oof[300:400])
    assert not np.allclose(got[:100], plain[:100])


def test_flag_rate_and_the_budget():
    scores = np.arange(100) / 100
    at_budget = rt.flag_rate(scores, 0.78)            # 0.78 to 0.99: 22 flagged
    assert (at_budget["flagged"], at_budget["n"], at_budget["rate"]) == (22, 100, 0.22)
    assert at_budget["low"] < 0.22 < at_budget["high"]
    assert rt.on_budget(at_budget, 0.22)
    assert not rt.on_budget(rt.flag_rate(scores, 0.65), 0.22)   # 35 of 100


def test_a_cutoff_reset_on_last_year_brings_a_drifted_year_back_to_budget():
    # Evenly spread scores, so the test does not depend on a random draw.
    last_year = np.linspace(0.3, 1.3, 400)               # scores drifted up by 0.3
    this_year = last_year + 0.001
    old_cutoff = 0.78                                    # flagged 22% before the drift
    assert not rt.on_budget(rt.flag_rate(this_year, old_cutoff), 0.22)
    new_cutoff = rm.alert_threshold(last_year, 0.22)
    assert rt.on_budget(rt.flag_rate(this_year, new_cutoff), 0.22)


def test_ranking_guard():
    rng = np.random.default_rng(0)
    y = np.zeros(400, bool)
    y[rng.choice(400, 40, replace=False)] = True
    groups = [f"p{i % 150}" for i in range(400)]
    good = y + rng.random(400) * 0.5
    assert rt.ranking_guard(np.zeros(400, bool), good, good, groups) == "not judged"
    assert rt.ranking_guard(y, good, good, groups, n=200) == "not worse"
    assert rt.ranking_guard(y, -good, good, groups, n=200) == "clearly worse"


@pytest.mark.parametrize("cutoff, retrain, outcome", [
    (True, True, "new cutoff"),      # both pass: the smaller change wins
    (True, False, "new cutoff"),
    (False, True, "retrain"),
    (False, False, "none passed"),
])
def test_winner(cutoff, retrain, outcome):
    assert rt.winner(cutoff, retrain) == outcome


REPLAYED = [(D(y, 1, 1), "replay") for y in range(2021, 2027)]


@pytest.mark.parametrize("as_of, mode, done, ok", [
    (D(2021, 1, 1), "replay", [], True),                        # the first replay
    (D(2022, 1, 1), "replay", [], False),                       # skips 2021
    (D(2022, 1, 1), "replay", REPLAYED[:1], True),              # the next one
    (D(2023, 1, 1), "replay", REPLAYED[:1], False),             # skips 2022
    (D(2021, 1, 1), "replay", REPLAYED[:1], False),             # a repeat
    (D(2027, 1, 1), "replay", REPLAYED, False),                 # replay is complete
    (D(2026, 7, 15), "live", REPLAYED[:5], False),              # replay not complete
    (D(2026, 7, 15), "live", REPLAYED, True),
    (D(2026, 7, 15), "live", REPLAYED + [(D(2026, 7, 15), "live")], False),  # a repeat
])
def test_order_guard(as_of, mode, done, ok):
    assert (rt.order_problem(as_of, mode, done) is None) is ok


def test_shifted_features_names_a_planted_shift():
    reference, window = _signals(n=600, seed=1), _signals(n=600, seed=2)
    before = set(rt.shifted_features(reference, window))
    window = window.assign(age_at_admit=window["age_at_admit"] + 25)
    assert set(rt.shifted_features(reference, window)) - before == {"age_at_admit"}
