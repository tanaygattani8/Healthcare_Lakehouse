"""Made-up rows only (CLAUDE.md: never a real small count in a fixture)."""
import numpy as np
import pandas as pd
import pytest

from scripts import readmission_model as rm


def _signals(n=400, seed=0):
    rng = np.random.default_rng(seed)
    admit = pd.Timestamp("2014-01-01") + pd.to_timedelta(rng.integers(0, 4400, n), unit="D")
    length = rng.integers(0, 10, n)
    return pd.DataFrame({
        "patient_id": [f"p{i % 150}" for i in range(n)],
        "stay_no": np.arange(n),
        "admit_year": admit.year,
        "admit_day": admit.date,
        "discharge_day": (admit + pd.to_timedelta(length, unit="D")).date,
        "age_at_admit": rng.integers(0, 91, n),
        "conditions_at_admit": rng.integers(0, 30, n),
        "length_of_stay_days": length,
        "prior_stays_12m": rng.integers(0, 3, n),
        "prior_emergency_12m": rng.integers(0, 3, n),
        "encounters_in_stay": rng.integers(1, 4, n),
        "days_since_last_discharge": np.where(rng.random(n) < 0.5, np.nan,
                                              rng.integers(1, 2000, n)),
        "has_diabetes": rng.random(n) < 0.2,
        "has_hypertension": rng.random(n) < 0.4,
        "has_cardiovascular_disease": rng.random(n) < 0.25,
        "is_planned": rng.random(n) < 0.3,
        "arrived_via_emergency": rng.random(n) < 0.3,
        "had_bypass_surgery": rng.random(n) < 0.1,
        "gender": rng.choice(["M", "F"], n),
        "admit_reason": rng.choice(["a", "b", "c", "rare"], n, p=[0.45, 0.3, 0.22, 0.03]),
        "stay_claim_cost": rng.random(n) * 1000,
        "post_followup_7d": rng.random(n) < 0.3,
        "outcome_readmitted_30d": rng.random(n) < 0.1,
    })


def _days(*pairs):
    return pd.DataFrame({"stay_no": range(len(pairs)),
                         "admit_day": [pd.Timestamp(a).date() for a, _ in pairs],
                         "discharge_day": [pd.Timestamp(d).date() for _, d in pairs]})


def test_split_boundaries():
    df = _days(("2019-11-20", "2019-12-01"),   # training: discharged on the cutoff
               ("2019-11-25", "2019-12-02"),   # gap: label would look into 2020
               ("2019-12-31", "2020-01-02"),   # gap: admitted in 2019
               ("2020-01-01", "2020-01-03"))   # production
    train, gap, prod = rm.split(df)
    assert list(train["stay_no"]) == [0]
    assert list(gap["stay_no"]) == [1, 2]
    assert list(prod["stay_no"]) == [3]


def test_no_bypass_drops_bypass_stays_and_its_feature():
    df = _signals()
    assert len(rm.population(df, "all")) == len(df)
    assert not rm.population(df, "no_bypass")["had_bypass_surgery"].any()
    assert "had_bypass_surgery" in rm.features_for("all")
    assert "had_bypass_surgery" not in rm.features_for("no_bypass")


def test_features_are_the_allowlist_with_flags_as_numbers():
    x = rm.build_features(_signals(), "all")
    assert list(x.columns) == rm.FEATURES
    assert x["has_diabetes"].isin([0, 1]).all()
    assert not {"patient_id", "stay_claim_cost", "post_followup_7d",
                "outcome_readmitted_30d"} & set(x.columns)


@pytest.mark.parametrize("leak", ["post_followup_7d", "outcome_readmitted_30d",
                                  "patient_id", "admit_day", "stay_claim_cost"])
def test_a_leak_added_to_the_allowlist_is_refused(monkeypatch, leak):
    monkeypatch.setattr(rm, "FEATURES", rm.FEATURES + [leak])
    with pytest.raises(ValueError, match=leak):
        rm.build_features(_signals(), "all")


def test_recall_at_count_hand_worked():
    y = [1, 0, 1, 0, 0, 1]
    score = [0.9, 0.8, 0.1, 0.7, 0.2, 0.6]
    # top 3: rows 0, 1, 3; one of the three readmissions
    assert rm.recall_at_count(y, score, 3) == pytest.approx(1 / 3)
    assert rm.recall_at_count(y, score, 0) == 0
    assert rm.recall_at_count([0, 0], [0.5, 0.4], 1) == 0


def test_ties_are_broken_by_input_order():
    assert list(rm.top_k([1, 1, 1, 0], 2)) == [True, True, False, False]


def test_bootstrap_resamples_patients_not_stays():
    # 20 readmitted stays of one patient: the model catches them, the rule
    # does not. 80 single-stay patients both score alike. Resampling that
    # patient as one unit must swing the difference more than 20 strangers.
    y = np.r_[np.ones(20), np.tile([1, 0, 0, 0, 0, 0, 0, 0], 10)]
    a = np.r_[np.ones(20), np.linspace(0, 0.5, 80)]
    b = np.r_[np.zeros(20), np.linspace(0, 0.5, 80)]
    clustered = ["p0"] * 20 + [f"q{i}" for i in range(80)]
    separate = [f"s{i}" for i in range(100)]
    low_c, _, high_c = rm.bootstrap_difference(y, a, b, 30, clustered, n=300)
    low_s, _, high_s = rm.bootstrap_difference(y, a, b, 30, separate, n=300)
    assert high_c - low_c > high_s - low_s


def test_verdict_branches():
    assert rm.verdict(0.01, 34) == "beats"
    assert rm.verdict(-0.10, 34) == "no better"
    assert rm.verdict(0.50, 15) == "too few to judge"


@pytest.mark.parametrize("kind", ["logistic", "boosting"])
def test_pipeline_fits_and_scores(kind):
    df = _signals()
    params = rm.GRID[kind][0]
    pipe = rm.build_pipeline(kind, params, "all").fit(rm.build_features(df, "all"),
                                                       df[rm.TARGET].astype(int))
    p = pipe.predict_proba(rm.build_features(df, "all"))[:, 1]
    assert p.shape == (len(df),) and ((p >= 0) & (p <= 1)).all()


def test_an_admit_reason_first_seen_in_production_does_not_crash():
    df = _signals()
    pipe = rm.build_pipeline("logistic", {"C": 1}, "no_bypass").fit(
        rm.build_features(df, "no_bypass"), df[rm.TARGET].astype(int))
    later = df.head(5).assign(admit_reason="COVID-19")
    assert pipe.predict_proba(rm.build_features(later, "no_bypass")).shape == (5, 2)


def test_cv_scores_every_grid_point():
    rows = rm.cv_scores(_signals(), "all")
    assert len(rows) == sum(len(g) for g in rm.GRID.values())
    assert all(0 <= r["cv_ap"] <= 1 for r in rows)


def test_alert_threshold_flags_the_share():
    scores = np.arange(100) / 100
    assert (scores >= rm.alert_threshold(scores, 0.25)).sum() == 25


def test_rule_probability_is_the_training_rate_of_each_side():
    train = pd.DataFrame({"has_cardiovascular_disease": [1, 1, 0, 0, 0, 0],
                          rm.TARGET: [True, False, True, False, False, False]})
    prod = pd.DataFrame({"has_cardiovascular_disease": [0, 1]})
    assert list(rm.rule_probability(train, prod)) == pytest.approx([0.25, 0.5])


def test_evaluate_rows():
    rng = np.random.default_rng(1)
    n = 200
    y = rng.random(n) < 0.1          # ~13 new and ~7 returning: both under TOO_FEW
    groups = [f"p{i // 2}" for i in range(n)]
    returning = np.arange(n) % 3 == 0
    rule = (rng.random(n) < 0.25).astype(int)
    model = rng.random(n)
    rows = rm.evaluate(y, groups, returning, int(rule.sum()),
                       {"rule": (rule, rule * 0.3), "model": (model, model)},
                       base_rate=0.1, name="all")
    assert len(rows) == 9                                   # 3 scorers x all/new/returning
    base = rows[0]
    assert base["scorer"] == "base_rate" and base["recall"] == pytest.approx(rule.sum() / n)
    model_all = next(r for r in rows if r["scorer"] == "model" and r["patients"] == "all")
    assert model_all["diff_low"] <= model_all["diff_mid"] <= model_all["diff_high"]
    assert model_all["model_verdict"] in {"beats", "no better", "too few to judge"}
    assert all("model_verdict" not in r for r in rows if r["scorer"] == "rule")
    assert {r["model_verdict"] for r in rows
            if r["scorer"] == "model" and r["patients"] != "all"} == {"too few to judge"}
    assert set().union(*rows) <= set(rm.RESULT_COLUMNS)