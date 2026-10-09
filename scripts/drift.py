"""Phase 6 drift: how far production has moved from training; pure Python."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.readmission_story import wilson

BINS = 10           # number bins, edges from training quantiles
FLOOR = 1e-4        # an empty bin's share, so the log never sees 0
WATCH, SHIFTED = 0.1, 0.25
UNSEEN = "<unseen>"
# A true/false rate that moved less than this, though significantly, is "watch".
MATERIAL = 0.05


def _labels(train: pd.Series, prod: pd.Series, kind: str) -> list[np.ndarray]:
    if kind == "number":
        edges = np.unique(train.quantile(np.linspace(0, 1, BINS + 1)[1:-1]).dropna())
        # Missing is bin -1; right-closed bins keep a shared value like 0 in its own bin (D72).
        return [np.where(s.isna(), -1, np.searchsorted(edges, s.to_numpy(float), side="left"))
                for s in (train, prod)]
    known = set(train.astype(str))
    return [s.astype(str).where(s.astype(str).isin(known), UNSEEN).to_numpy()
            for s in (train, prod)]


def psi(train, prod, kind: str) -> float:
    """Population stability index: sum of (q - p) * ln(q / p) over bins."""
    a, b = _labels(pd.Series(train), pd.Series(prod), kind)
    order = sorted(set(a) | set(b), key=str)
    p, q = (pd.Series(s).value_counts(normalize=True).reindex(order, fill_value=0)
            .clip(lower=FLOOR).to_numpy() for s in (a, b))
    return float(np.sum((q - p) * np.log(q / p)))


def status(value: float) -> str:
    if value < WATCH:
        return "stable"
    return "watch" if value <= SHIFTED else "shifted"


def drift_report(train: pd.DataFrame, prod: pd.DataFrame, kinds: dict[str, str]) -> list[dict]:
    """One row per feature; a flag's status comes from its rate, since PSI barely moves on 0/1."""
    rows = []
    for feature, kind in kinds.items():
        value = psi(train[feature], prod[feature], "category" if kind == "flag" else kind)
        state = (rate_status(float(train[feature].mean()), int(prod[feature].sum()), len(prod))
                 if kind == "flag" else status(value))
        rows.append({"feature": feature, "psi": value, "status": state})
    return rows


def interval_status(reference: float, k: int, n: int) -> str:
    """'shifted' if the reference rate is outside this window's 95% Wilson interval."""
    low, high = wilson(k, n)
    return "stable" if low <= reference <= high else "shifted"


def rate_status(reference: float, k: int, n: int) -> str:
    """A flag's status: stable inside the 95% interval, else shifted at 5+ points, else watch."""
    if interval_status(reference, k, n) == "stable":
        return "stable"
    return "shifted" if abs(k / n - reference) >= MATERIAL else "watch"
