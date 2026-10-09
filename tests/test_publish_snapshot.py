import datetime as dt

import numpy as np
import pandas as pd
import pytest

from scripts.publish_snapshot import (
    check_only_categories,
    check_roles,
    check_small_cells,
    ops_queries,
    publish_drift,
    publish_model_results,
    publish_ops,
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


def test_hidden_levels_that_sum_to_1_to_10_stop_the_publish():
    levels = pd.DataFrame({
        "signal": ["g"] * 4, "suppressed": [False, False, True, True],
        "index_stays": [500, 400, None, None], "readmitted": [20, 30, None, None],
        "rest_stays": [600, 700, None, None], "rest_readmitted": [36, 26, None, None]})
    with pytest.raises(SystemExit, match="between them"):
        check_small_cells(levels)
    check_small_cells(levels.assign(rest_readmitted=[45, 35, None, None]))


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
        "model_verdict": ["beats", "too few to judge", None, None],
        "cut_low": [0.02, None, None, None], "cut_mid": [0.1, None, None, None],
        "cut_high": [0.2, None, None, None],
        "cutoff_verdict": ["beats", None, None, None]})


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



# Phase 8's dashboard, published for the app's Operations chapter.
def _ops_raw(**over):
    raw = {
        "kpi_visits": pd.DataFrame({"visits": [54000], "visits_prior": [54500],
                                    "visits_change_pct": [-0.9],
                                    "visits_share_of_network_pct": [100.0]}),
        "kpi_stays": pd.DataFrame({"stays": [497], "stays_prior": [469],
                                   "stays_change_pct": [6.0], "cost_per_stay": [24200],
                                   "cost_vs_network_pct": [0.0]}),
        "kpi_readmission": pd.DataFrame({"readmission_rate_pct_2020_2026": [1.39],
                                         "readmission_rate_pct_2010_2019": [1.49]}),
        "kpi_window": pd.DataFrame({"window_start": [dt.date(2025, 8, 1)],
                                    "last_month": [dt.date(2026, 7, 1)],
                                    "prior_start": [dt.date(2024, 8, 1)],
                                    "prior_end": [dt.date(2025, 7, 1)]}),
        "visits_trend": pd.DataFrame({"visit_month": [dt.date(2026, 7, 1)] * 2,
                                      "visit_type": ["inpatient", "wellness"],
                                      "visits": [40, 900]}),
        "stays_trend": pd.DataFrame({"admit_quarter": [dt.date(2026, 4, 1)], "stays": [120],
                                     "avg_length_of_stay_days": [5.1],
                                     "cost_per_stay": [24000]}),
        "by_payer": pd.DataFrame({"payer": ["Medicare", "Humana", "NO_INSURANCE", "Aetna",
                                            "Cigna Health"],
                                  "stays": [400, 40, None, None, None],
                                  "avg_length_of_stay_days": [5.4, 3.6, None, None, None],
                                  "cost_per_stay": [32034, 13434, None, None, None]}),
        "by_hospital": pd.DataFrame({"hospital": ["CAPE COD HOSPITAL INC, HYANNIS",
                                                  "TEWKSBURY HOSPITAL, TEWKSBURY"],
                                     "stays": [300, 150], "avg_length_of_stay_days": [6.1, 6.5],
                                     "cost_per_stay": [33256, 2201]}),
    }
    return {**raw, **over}


def test_ops_publish_replaces_real_names():
    out = publish_ops(_ops_raw())
    assert list(out["ops_payers"]["payer"]) == ["Medicare", "Commercial payer 1", "No insurance",
                                                "Commercial payer 2", "Commercial payer 3"]
    assert list(out["ops_hospitals"]["hospital"]) == ["Hospital A", "Hospital B"]
    text = " ".join(str(v) for f in out.values() for v in f.to_numpy().ravel())
    for real in ("Humana", "Aetna", "Cigna", "CAPE COD", "TEWKSBURY"):
        assert real not in text


def test_ops_publish_drops_the_always_100_share_and_network_gaps():
    kpi = publish_ops(_ops_raw())["ops_kpi"]
    assert "visits_share_of_network_pct" not in kpi
    assert "cost_vs_network_pct" not in kpi
    assert kpi["window_start"].iloc[0] == pd.Timestamp(2025, 8, 1)


@pytest.mark.parametrize("over", [
    # A hidden trend cell: the 12-month tiles would give it back by subtraction.
    {"visits_trend": pd.DataFrame({"visit_month": [dt.date(2026, 7, 1)],
                                   "visit_type": ["other"], "visits": [None]})},
    # A shown count of 1-10.
    {"by_hospital": pd.DataFrame({"hospital": ["X"], "stays": [7],
                                  "avg_length_of_stay_days": [5.0], "cost_per_stay": [1.0]})},
    # Hospitals left out (1-10 stays each) that add up to 1-10 against the tile.
    {"by_hospital": pd.DataFrame({"hospital": ["X"], "stays": [490],
                                  "avg_length_of_stay_days": [5.0], "cost_per_stay": [1.0]})},
    # Exactly one hidden payer: the tile minus the rest is its count.
    {"by_payer": pd.DataFrame({"payer": ["Medicare", "Aetna"], "stays": [450, None],
                               "avg_length_of_stay_days": [5.4, None],
                               "cost_per_stay": [1.0, None]})},
])
def test_ops_publish_refuses_what_subtraction_gives_back(over):
    with pytest.raises(SystemExit):
        publish_ops(_ops_raw(**over))


def test_ops_queries_are_the_dashboards_own():
    queries = ops_queries("healthcare_dev")
    assert set(queries) == {"kpi_visits", "kpi_stays", "kpi_readmission", "visits_trend",
                            "stays_trend", "by_payer", "by_hospital"}
    sql, params = queries["by_payer"]
    assert "metrics.shown(" in sql and set(params.values()) == {"All"}


def test_every_committed_snapshot_has_a_role_for_every_number():
    from pathlib import Path
    folder = Path(__file__).resolve().parents[1] / "snapshots"
    check_roles({p.stem: pd.read_parquet(p) for p in folder.glob("*.parquet")})


def test_an_undeclared_number_column_stops_the_publish():
    with pytest.raises(SystemExit, match="no declared role"):
        check_roles({"ops_visits": pd.DataFrame({"visits": [500], "new_count": [40]})})
    with pytest.raises(SystemExit, match="no declared role"):
        check_roles({"a_new_frame": pd.DataFrame({"n": [500]})})


def test_a_count_of_1_to_10_stops_the_publish_but_businesses_do_not():
    with pytest.raises(SystemExit, match="1-10"):
        check_roles({"bronze_counts": pd.DataFrame({"layer": ["quarantine"],
                                                    "entity": ["patient"], "rows": [3]})})
    check_roles({"bronze_counts": pd.DataFrame({"layer": ["bronze"], "entity": ["payers"],
                                                "rows": [10]})})
    check_roles({"deid_kanon": pd.DataFrame({"groups": [2], "people": [8]})})

