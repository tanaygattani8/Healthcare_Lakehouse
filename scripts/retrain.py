"""Phase 9: retraining on drift, one cursor at a time (spec §2, §5).

Pure Python, like readmission_model.py and drift.py, so every rule is
tested on made-up rows (tests/test_retrain.py). The notebook
retrain_readmission.py runs it on gold, told "today is as_of".
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline

from scripts import drift
from scripts import readmission_model as rm
from scripts.readmission_story import wilson

POPULATION = "all"            # spec §0: no_bypass rests on 17 readmissions and stays at v2
FIRST_REPLAY = dt.date(2021, 1, 1)
LAST_REPLAY = dt.date(2026, 1, 1)
REPLAYS = LAST_REPLAY.year - FIRST_REPLAY.year + 1
LABEL_DAYS = 30               # a stay's 30-day outcome is known 30 days after discharge


def add_years(day: dt.date, n: int) -> dt.date:
    return (pd.Timestamp(day) + pd.DateOffset(years=n)).date()


def windows(as_of: dt.date) -> dict[str, tuple[dt.date, dt.date]]:
    """Admit-day bounds, start included, end excluded (spec §2.1)."""
    return {"check": (add_years(as_of, -1), as_of),
            "cutoff": (add_years(as_of, -2), add_years(as_of, -1))}


def admitted(df: pd.DataFrame, start, end) -> pd.Series:
    admit = pd.to_datetime(df["admit_day"])
    return (admit >= pd.Timestamp(start)) & (admit < pd.Timestamp(end))


def labels_known_by(as_of: dt.date) -> dt.date:
    """The last discharge day whose 30-day outcome is known on as_of."""
    return as_of - dt.timedelta(days=LABEL_DAYS)


def labelled(df: pd.DataFrame, as_of: dt.date) -> pd.Series:
    return pd.to_datetime(df["discharge_day"]) <= pd.Timestamp(labels_known_by(as_of))


def trained_on(df: pd.DataFrame, admit_before, discharged_by) -> pd.Series:
    """The stays a model with these two tags trained on. v2 has no tags; its
    training is split()'s: admit_before PROD_FROM, discharged_by TRAIN_UNTIL."""
    return ((pd.to_datetime(df["admit_day"]) < pd.Timestamp(admit_before))
            & (pd.to_datetime(df["discharge_day"]) <= pd.Timestamp(discharged_by)))


def budget(signals: pd.DataFrame) -> float:
    """The workload budget (spec §2.2): the rule's flag rate on phase 6's
    training stays, the share v2's cutoff was set to. Fixed for every cursor."""
    train, _, _ = rm.split(rm.population(signals, POPULATION))
    return float(rm.rule_score(train).mean())


def settings(source: Mapping[str, str]) -> tuple[str, dict]:
    """A model's kind and settings from its MLflow params or version tags,
    which are strings, cast back to the types in rm.GRID."""
    kind = source["kind"]
    return kind, {key: type(value)(source[key]) for key, value in rm.GRID[kind][0].items()}


def scored_from(tags: Mapping[str, str]) -> str:
    """The first admit day score_readmission scores for a champion: production,
    or after its training if that ends later, so a retrained champion never
    scores its own training stays (spec §3.3). ISO dates compare as text."""
    return max(tags.get("train_admit_before", rm.PROD_FROM), rm.PROD_FROM)


def window_scores(model, fresh: Pipeline, trained: pd.DataFrame,
                  window: pd.DataFrame) -> np.ndarray:
    """Scores for `window`, in its row order. Stays the model trained on get
    out-of-fold scores from `fresh`, an unfitted copy with the same settings:
    in-sample scores look surer than new stays will (D72, spec §2.4)."""
    score = pd.Series(model.predict_proba(rm.build_features(window, POPULATION))[:, 1],
                      index=window.index)
    seen = window.index.intersection(trained.index)
    if len(seen):
        oof = pd.Series(rm.oof_scores(fresh, trained, POPULATION), index=trained.index)
        score[seen] = oof[seen]
    return score.to_numpy()


def flag_rate(scores, threshold: float) -> dict:
    flagged, n = int((np.asarray(scores, float) >= threshold).sum()), len(scores)
    low, high = wilson(flagged, n)
    return {"rate": flagged / n, "low": low, "high": high, "flagged": flagged, "n": n}


def on_budget(rate: dict, target: float) -> bool:
    """The budget lies inside this flag rate's 95% Wilson interval (spec §2.3, §2.5)."""
    return drift.interval_status(target, rate["flagged"], rate["n"]) == "stable"


def ranking_guard(y, challenger, champion, groups, n: int = 1000, seed: int = 0) -> str:
    """"clearly worse" only if the whole 95% interval of the challenger's
    average precision minus the champion's, resampling patients, is below
    zero (spec §2.5). Resamples with no readmission have no average
    precision and are skipped. At ~5 readmissions a year this catches a gross
    failure, not a subtle one."""
    y = np.asarray(y, bool)
    if not y.any():
        return "not judged"
    a, b = np.asarray(challenger, float), np.asarray(champion, float)
    diffs = [average_precision_score(y[i], a[i]) - average_precision_score(y[i], b[i])
             for i in rm.patient_resamples(groups, n, seed) if y[i].any()]
    return "clearly worse" if np.percentile(diffs, 97.5) < 0 else "not worse"


def winner(cutoff_passes: bool, retrain_passes: bool) -> str:
    """The smaller change wins when both pass (spec §2.6)."""
    if cutoff_passes:
        return "new cutoff"
    return "retrain" if retrain_passes else "none passed"


def order_problem(as_of: dt.date, mode: str,
                  done: list[tuple[dt.date, str]]) -> str | None:
    """Why this run may not go ahead, or None (spec §5). `done` is every
    (as_of, mode) already in ml.retrain_history."""
    if (as_of, mode) in done:
        return f"{mode} {as_of} is already decided"
    replays = sorted(day for day, m in done if m == "replay")
    if mode == "replay":
        expected = add_years(replays[-1], 1) if replays else FIRST_REPLAY
        if expected > LAST_REPLAY:
            return "the replay is complete"
        return None if as_of == expected else f"the next replay is {expected}, not {as_of}"
    if len(replays) < REPLAYS:
        return f"a live run needs the {REPLAYS} replay rows; found {len(replays)}"
    return None


def shifted_features(reference: pd.DataFrame, window: pd.DataFrame) -> list[str]:
    """Features whose drift status is "shifted" in `window` against the stays
    the champion trained on. They explain a trigger; they trigger nothing
    (spec §2.3)."""
    x_ref = rm.build_features(reference, POPULATION)
    x_win = rm.build_features(window, POPULATION)
    kinds = {c: "number" if c in rm.NUMBERS else "flag" if c in rm.FLAGS else "category"
             for c in x_ref.columns}
    return [r["feature"] for r in drift.drift_report(x_ref, x_win, kinds)
            if r["status"] == "shifted"]
