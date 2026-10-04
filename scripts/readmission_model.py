from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.model_selection import GroupKFold, cross_val_predict, cross_val_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TRAIN_UNTIL = "2019-12-01"  # last discharge day in training: every label is known by 2020
PROD_FROM = "2020-01-01"    # first admit day in production
TOO_FEW = 30                # production readmissions needed for a verdict
MIN_REASON_STAYS = 20       # rarer admit reasons share one bucket, learned from training
NO_EARLIER_STAY = 3650      # days_since_last_discharge for a first stay; a flag says so

POPULATIONS = ("all", "no_bypass")
TARGET = "outcome_readmitted_30d"
NUMBERS = ["age_at_admit", "conditions_at_admit", "length_of_stay_days", "prior_stays_12m",
           "prior_emergency_12m", "encounters_in_stay", "days_since_last_discharge"]
FLAGS = ["has_diabetes", "has_hypertension", "has_cardiovascular_disease", "is_planned",
         "arrived_via_emergency",  # P3: delete this line if the probe dropped the feature
         "had_bypass_surgery"]
CATEGORIES = ["gender", "admit_reason"]
FEATURES = NUMBERS + FLAGS + CATEGORIES
# Never model inputs, whatever FEATURES says (spec §3.2).
NEVER = {"patient_id", "stay_no", "admit_year", "admit_day", "discharge_day", "stay_claim_cost"}
LEAK_PREFIXES = ("post_", "outcome_")
GRID = {
    "logistic": [{"C": c} for c in (0.01, 0.1, 1)],
    "boosting": [{"max_depth": d, "learning_rate": r} for d in (2, 3) for r in (0.05, 0.1)],
}
# ml.model_results, in order (decision P-c).
RESULT_COLUMNS = ["population", "patients", "scorer", "model_kind", "model_version",
                  "readmitted", "caught", "missed", "k", "recall", "avg_precision", "brier",
                  "cv_avg_precision", "diff_low", "diff_mid", "diff_high", "model_verdict"]


def population(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """'all' is every index stay; 'no_bypass' drops stays with bypass surgery."""
    return df if name == "all" else df[~df["had_bypass_surgery"].astype(bool)]


def split(df: pd.DataFrame, train_until: str = TRAIN_UNTIL,
          prod_from: str = PROD_FROM) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Training, gap, production (spec §2). The gap's 30-day labels would
    look past the cutoff, so it is used for nothing."""
    admit = pd.to_datetime(df["admit_day"])
    discharge = pd.to_datetime(df["discharge_day"])
    before = admit < pd.Timestamp(prod_from)
    train = before & (discharge <= pd.Timestamp(train_until))
    return df[train], df[before & ~train], df[~before]


def features_for(name: str) -> list[str]:
    # In "no_bypass" the bypass flag is always false.
    return [c for c in FEATURES if not (name == "no_bypass" and c == "had_bypass_surgery")]


def build_features(df: pd.DataFrame, name: str) -> pd.DataFrame:
    columns = features_for(name)
    leaks = [c for c in columns if c in NEVER or c.startswith(LEAK_PREFIXES)]
    if leaks:
        raise ValueError(f"not model inputs: {leaks}")
    x = df[columns].copy()
    flags = [c for c in FLAGS if c in columns]
    x[flags] = x[flags].astype(int)
    x[CATEGORIES] = x[CATEGORIES].astype(str)
    return x


def build_pipeline(kind: str, params: dict, name: str) -> Pipeline:
    """Everything that depends on the data's spread (fill, scale, which
    reasons are rare) is fitted inside, on training rows only (spec §3.3)."""
    columns = features_for(name)
    prep = ColumnTransformer([
        ("numbers", make_pipeline(SimpleImputer(strategy="constant", fill_value=NO_EARLIER_STAY,
                                                add_indicator=True), StandardScaler()),
         [c for c in NUMBERS if c in columns]),
        ("flags", "passthrough", [c for c in FLAGS if c in columns]),
        ("categories", OneHotEncoder(min_frequency=MIN_REASON_STAYS,
                                     handle_unknown="infrequent_if_exist", sparse_output=False),
         CATEGORIES),
    ])
    model = (LogisticRegression(max_iter=1000, **params) if kind == "logistic"
             else HistGradientBoostingClassifier(max_iter=200, random_state=0, **params))
    return Pipeline([("prep", prep), ("model", model)])


def cv_scores(df: pd.DataFrame, name: str, folds: int = 5) -> list[dict]:
    """Every grid point's average precision over patient-grouped folds.
    Chosen on this, not recall at 25%, which moves in 5-point steps with
    ~20 readmissions per fold (spec §4.3)."""
    x, y = build_features(df, name), df[TARGET].astype(int)
    rows = []
    for kind, grid in GRID.items():
        for params in grid:
            scores = cross_val_score(build_pipeline(kind, params, name), x, y,
                                     groups=df["patient_id"], cv=GroupKFold(folds),
                                     scoring="average_precision")
            rows.append({"kind": kind, "params": params, "cv_ap": float(scores.mean()),
                         "cv_ap_sd": float(scores.std())})
    return rows


def oof_scores(pipe: Pipeline, df: pd.DataFrame, name: str, folds: int = 5) -> np.ndarray:
    """Each training stay scored by a copy of `pipe` fitted on the other
    patients' folds. The alert cutoff and the drift reference use these: a
    model scoring the stays it was fitted on looks surer than it will be on
    new ones, and that gap would read as drift (D72)."""
    return cross_val_predict(clone(pipe), build_features(df, name), df[TARGET].astype(int),
                             groups=df["patient_id"], cv=GroupKFold(folds),
                             method="predict_proba")[:, 1]


def rule_score(df: pd.DataFrame) -> np.ndarray:
    """The baseline (D69): heart disease or stroke on the admit day."""
    return df["has_cardiovascular_disease"].astype(int).to_numpy()


def rule_probability(train: pd.DataFrame, prod: pd.DataFrame) -> np.ndarray:
    """The rule as a probability, for its Brier score: each side's training rate."""
    rates = train[TARGET].astype(float).groupby(rule_score(train)).mean()
    return (pd.Series(rule_score(prod)).map(rates)
            .fillna(train[TARGET].mean()).to_numpy(float))


def alert_threshold(scores, share: float) -> float:
    """The score that flags `share` of training stays: the only cutoff a
    deployment would have (spec §4.3)."""
    return float(np.quantile(scores, 1 - share))


def top_k(score, k: int) -> np.ndarray:
    """The k highest scores; ties go to the earlier row."""
    flagged = np.zeros(len(score), bool)
    flagged[np.argsort(-np.asarray(score, float), kind="stable")[:k]] = True
    return flagged


def recall_at_count(y, score, k: int) -> float:
    y = np.asarray(y, bool)
    return float((top_k(score, k) & y).sum() / y.sum()) if y.any() else 0.0


def bootstrap_difference(y, model, rule, groups, n: int = 1000,
                         seed: int = 0) -> tuple[float, float, float]:
    """95% interval of recall(model) - recall(rule), resampling patients, so
    one patient's many stays move together. In each resample both flag as
    many stays as the 0/1 rule flags there (decision P-f, as revised in D72:
    rescaling one k moved the rule off its own count)."""
    y, a, b = np.asarray(y, bool), np.asarray(model, float), np.asarray(rule, float)
    _, patient = np.unique(np.asarray(groups), return_inverse=True)
    order = np.argsort(patient, kind="stable")
    rows_of = np.split(order, np.cumsum(np.bincount(patient))[:-1])
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        idx = np.concatenate([rows_of[i] for i in rng.integers(0, len(rows_of), len(rows_of))])
        k_r = int(np.count_nonzero(b[idx]))
        diffs.append(recall_at_count(y[idx], a[idx], k_r) - recall_at_count(y[idx], b[idx], k_r))
    low, mid, high = np.percentile(diffs, [2.5, 50, 97.5])
    return float(low), float(mid), float(high)


def verdict(low: float, readmitted: int) -> str:
    if readmitted < TOO_FEW:
        return "too few to judge"
    return "beats" if low > 0 else "no better"


def evaluate(y, groups, returning, k: int, scorers: dict, base_rate: float,
             name: str) -> list[dict]:
    """Rows for ml.model_results (spec §4.3): the base rate, then each
    scorer, for all, new and returning patients. scorers maps a name to
    (score, probability) and must hold 'rule', the comparison. Flags are the
    top k over all of production; a breakdown counts within its patients."""
    y = np.asarray(y, bool)
    groups = np.asarray(groups)
    returning = np.asarray(returning, bool)
    rule = np.asarray(scorers["rule"][0], float)
    rows = []
    for patients, mask in (("all", np.ones(len(y), bool)), ("new", ~returning),
                           ("returning", returning)):
        truth = y[mask].astype(int)
        readmitted = int(truth.sum())
        # Flagging k of n at random catches k/n on average (decision P-e).
        rows.append({"population": name, "patients": patients, "scorer": "base_rate",
                     "readmitted": readmitted, "k": k, "recall": k / len(y),
                     "avg_precision": truth.mean(),
                     "brier": brier_score_loss(truth, np.full(len(truth), base_rate))})
        for scorer, (score, prob) in scorers.items():
            score, prob = np.asarray(score, float), np.asarray(prob, float)
            caught = int((top_k(score, k) & y & mask).sum())
            row = {"population": name, "patients": patients, "scorer": scorer,
                   "readmitted": readmitted, "caught": caught, "missed": readmitted - caught,
                   "k": k, "recall": caught / readmitted if readmitted else np.nan,
                   "avg_precision": (average_precision_score(truth, score[mask])
                                     if readmitted else np.nan),
                   "brier": brier_score_loss(truth, prob[mask])}
            if scorer != "rule" and patients == "all":
                low, mid, high = bootstrap_difference(y, score, rule, groups)
                row |= {"diff_low": low, "diff_mid": mid, "diff_high": high,
                        "model_verdict": verdict(low, readmitted)}
            elif scorer != "rule":
                # No bootstrap for a breakdown (decision P-j).
                row["model_verdict"] = "too few to judge" if readmitted < TOO_FEW else None
            rows.append(row)
    return rows