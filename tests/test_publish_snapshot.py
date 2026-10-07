import numpy as np
import pandas as pd
import pytest

from scripts.publish_snapshot import (
    check_only_categories,
    check_small_cells,
    publish_drift,
    publish_model_results,
    publish_retrain_history,
)


def test_counts_and_known_labels_pass():
    check_only_categories(pd.DataFrame({"stage": ["llm"], "phi_category": ["name"],
                                        "recall": [0.996]}))


def test_a_name_in_any_text_column_is_refused():
    # The failure this exists for: a join mistake that carries surface_text,
    # or a label column that picked up a real value.
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"stage": ["llm"], "phi_category": ["Lucius"]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"surface_text": ["Lucius"]}))


def test_care_gap_measures_are_known_labels():
    # gold_care_gap's only text column; a measure missing from ALLOWED_TEXT
    # would stop the publish.
    check_only_categories(pd.DataFrame({"measure": ["diabetes_hba1c", "bp_control",
                                                    "statin_therapy"], "gaps": [17, 58, 1]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"measure": ["statin_therapy", "Lucius"]}))


def test_story_labels_are_known_and_nothing_else_passes():
    check_only_categories(pd.DataFrame({
        "signal": ["age_band", "prior_stays_12m_band", "admit_period"],
        "level": ["80+", "2+", "2010-2019"], "index_stays": [120, 60, 31]}))
    check_only_categories(pd.DataFrame({"decision": ["NO-GO"], "shortlisted": [1]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"signal": ["patient_id"]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"level": ["Lucius"]}))


def test_eval_labels_are_known_and_nothing_else_passes():
    check_only_categories(pd.DataFrame({
        "set_name": ["dev", "test"], "contestant": ["raw", "genie"],
        "verdict": ["correct", "answered_unanswerable"], "answers": [3, 1]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"contestant": ["raw", "gpt"]}))


def _levels(**cols):
    base = {"signal": ["gender", "gender"], "suppressed": [False, False],
            "index_stays": [500, 600], "readmitted": [20, 30],
            "rest_stays": [600, 500], "rest_readmitted": [30, 20]}
    return pd.DataFrame(base | cols)


def test_published_levels_pass_when_every_shown_count_is_0_or_11_plus():
    check_small_cells(_levels())
    check_small_cells(_levels(readmitted=[0, 30], rest_readmitted=[30, 0]))


def test_a_shown_count_of_1_to_10_stops_the_publish():
    with pytest.raises(SystemExit):
        check_small_cells(_levels(readmitted=[7, 30]))


def test_a_lone_hidden_level_stops_the_publish():
    with pytest.raises(SystemExit):
        check_small_cells(_levels(suppressed=[True, False]))


def _results():
    # Made-up counts: one row safe, one with 1-10 caught, one with 1-10 missed,
    # and a base-rate row, which has no caught or missed. None, not NaN, is how
    # the SQL connector returns a NULL.
    return pd.DataFrame({
        "population": ["all", "all", "no_bypass", "all"],
        "patients": ["all", "new", "all", "all"],
        "scorer": ["model", "model", "rule", "base_rate"],
        "model_kind": ["logistic", "logistic", None, None],
        "model_version": ["3", "3", None, None],
        "readmitted": [40, 30, 25, 40], "caught": [25.0, 4.0, 20.0, None],
        "missed": [15.0, 26.0, 5.0, None], "k": [600, 600, 500, 600],
        "recall": [25 / 40, 4 / 30, 20 / 25, 0.25], "avg_precision": [0.1, 0.1, 0.1, 0.02],
        "brier": [0.02] * 4, "cv_avg_precision": [0.1, 0.1, None, None],
        "diff_low": [0.01, None, None, None], "diff_mid": [0.1, None, None, None],
        "diff_high": [0.2, None, None, None],
        "model_verdict": ["beats", "too few to judge", None, None]})


def test_recall_on_1_to_10_caught_or_missed_is_hidden_and_no_count_is_published():
    out = publish_model_results(_results())
    assert list(out["recall"].isna()) == [False, True, True, False]
    # The "new" row is a breakdown: its verdict only, never a number (D66:
    # the base rate's precision there would be readmitted / stays).
    numbers = out.drop(columns=["population", "patients", "scorer", "model_kind",
                                "model_verdict"])
    assert numbers.iloc[1].isna().all() and out["model_verdict"][1] == "too few to judge"
    assert (out["avg_precision"].dropna() == out["avg_precision"].dropna().round(4)).all()
    # The rule row (index 2) has 1-10 missed. A 0/1 rule's average precision
    # is c^2/(R*F) + (R-c)/N, so it gives the caught count back; Brier too.
    assert np.isnan(out["avg_precision"][2]) and np.isnan(out["brier"][2])
    # The model's average precision is a ranking score, not a count: kept.
    assert out["avg_precision"][0] == 0.1
    assert not {"readmitted", "caught", "missed", "k", "model_version"} & set(out.columns)
    assert out["diff_low"].dtype == float
    check_only_categories(out)


def test_drift_numbers_with_nulls_stay_numbers():
    out = publish_drift(pd.DataFrame({
        "drift_check": ["feature", "flag_rate"], "period": ["2020-2026", "2023"],
        "subject": ["admit_reason", "no_bypass"], "value": [0.62, 0.31],
        "low": [None, 0.27], "high": [None, 0.36], "status": ["shifted", "shifted"]}))
    assert np.isnan(out["low"][0])
    # Rounded, so a training rate cannot be turned back into exact counts.
    assert out["value"].tolist() == [0.62, 0.31]
    # The training readmission rate is not published: with the totals it
    # narrows the gap's 1-10 readmissions to a handful (D72).
    rates = publish_drift(pd.DataFrame({
        "drift_check": ["readmission_rate"] * 2, "period": ["training", "2020-2026"],
        "subject": ["all"] * 2, "value": [0.0126, 0.0139], "low": [0.0104, 0.0099],
        "high": [0.0153, 0.0194], "status": ["reference", "stable"]}))
    assert rates["period"].tolist() == ["2020-2026"] and rates["value"].tolist() == [0.014]
    check_only_categories(out)


def test_model_labels_are_known_and_nothing_else_passes():
    check_only_categories(pd.DataFrame({
        "drift_check": ["feature", "readmission_rate"], "period": ["2020-2026", "training"],
        "subject": ["has_cardiovascular_disease", "all"], "status": ["shifted", "reference"],
        "value": [0.09, 0.0126]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"subject": ["patient_id"]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"model_verdict": ["probably"]}))


def _history(**overrides):
    row = {"as_of": "2021-01-01", "mode": "replay", "champion_version": "2",
           "check_stays": 434, "target": 0.218, "champion_rate": 0.316,
           "champion_low": 0.274, "champion_high": 0.361, "triggered": True,
           "cutoff_rate": 0.23, "cutoff_workload": "pass", "retrain_rate": 0.237,
           "retrain_workload": "pass", "retrain_ranking": "not worse",
           "outcome": "new cutoff", "new_version": "4",
           "shifted_features": "conditions_at_admit,admit_reason"}
    return pd.DataFrame([row | overrides])


def test_retrain_history_publishes_rates_and_known_labels():
    out = publish_retrain_history(_history())
    assert out["as_of"].dtype.kind == "M" and out["champion_rate"][0] == 0.316
    assert out["shifted_features"][0] == "conditions_at_admit,admit_reason"
    # A row that was not triggered has no challenger: NULLs stay numbers.
    quiet = publish_retrain_history(_history(triggered=False, cutoff_rate=None,
                                             cutoff_workload=None, outcome="no trigger"))
    assert np.isnan(quiet["cutoff_rate"][0])


@pytest.mark.parametrize("bad", [
    {"shifted_features": "patient_id"},          # not a feature name
    {"outcome": "Jane Doe"},                     # not a known label
    {"check_stays": 7},                          # a 1-10 count (D66)
    {"champion_rate": 0.02},                     # 0.02 x 434 flags 1-10 stays
])
def test_retrain_history_refuses_what_it_does_not_know(bad):
    with pytest.raises(SystemExit):
        publish_retrain_history(_history(**bad))

