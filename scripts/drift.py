"""Phase 6 drift (spec §6): how far production has moved from training.

Pure Python, so a planted shift can prove the check fires
(tests/test_drift.py). The notebook drift_readmission.py runs it on gold.
"""

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
        # Missing is its own bin (-1): a first stay has no days since the last one.
        # Left: bins are (e[i-1], e[i]], so a value most rows share (0 prior
        # stays) keeps a bin of its own instead of absorbing 1, 2, ... (D72).
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
    """One row per feature. kind is "number", "category" or "flag" (0/1).
    A flag's PSI is still reported, but its status comes from its rate:
    PSI barely moves on a two-value column (22% to 35% scores 0.09)."""
    rows = []
    for feature, kind in kinds.items():
        value = psi(train[feature], prod[feature], "category" if kind == "flag" else kind)
        state = (rate_status(float(train[feature].mean()), int(prod[feature].sum()), len(prod))
                 if kind == "flag" else status(value))
        rows.append({"feature": feature, "psi": value, "status": state})
    return rows


def interval_status(reference: float, k: int, n: int) -> str:
    """'shifted' if the reference rate is outside this window's 95% Wilson
    interval (decision P-i)."""
    low, high = wilson(k, n)
    return "stable" if low <= reference <= high else "shifted"


def rate_status(reference: float, k: int, n: int) -> str:
    """A true/false feature's status: "stable" inside this window's 95%
    interval; outside it, "shifted" if the rate moved 5 points or more, else
    "watch" (with ~2,450 stays, a 3-point move is already significant)."""
    if interval_status(reference, k, n) == "stable":
        return "stable"
    return "shifted" if abs(k / n - reference) >= MATERIAL else "watch"
