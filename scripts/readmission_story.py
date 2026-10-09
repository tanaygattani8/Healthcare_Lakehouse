"""Chapter 5's rule, fixed before any number was seen: which levels separate, GO or NO-GO."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

MIN_STAYS = 30          # index stays on each side of a comparison
MIN_PATIENTS = 10       # distinct readmitted patients on the higher-rate side
MIN_SIGNALS = 2         # shortlisted signals needed for GO
SUPPRESS_BELOW = 11     # index stays or readmissions of 1-10 are not published (D66)
Z = 1.96                # 95%

# Each dimension of metrics.readmission, and the chapter it belongs to (spec §2).
SIGNALS = {
    "admit_period": 1,
    "age_band": 2, "gender": 2, "has_diabetes": 2, "has_hypertension": 2,
    "has_cardiovascular_disease": 2, "above_median_conditions": 2,
    "admit_reason_group": 3, "is_planned": 3, "above_median_length_of_stay": 3,
    "prior_stays_12m_band": 3, "prior_emergency_12m_band": 3, "post_followup_7d": 3,
}
# Shown, never shortlisted: not known at discharge; the prefixes guard new ones.
NOT_AT_DISCHARGE = {"admit_period", "post_followup_7d"}
LEAK_PREFIXES = ("post_", "outcome_")


@dataclass(frozen=True)
class Side:
    stays: int
    readmitted: int
    readmitted_patients: int

    @property
    def rate(self) -> float:
        return self.readmitted / self.stays if self.stays else 0.0


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    """Wilson interval for k of n; stays inside 0-1."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def separates(level: Side, rest: Side) -> bool:
    """Enough stays both sides, enough people behind the higher rate, intervals apart."""
    if min(level.stays, rest.stays) < MIN_STAYS:
        return False
    if max(level, rest, key=lambda side: side.rate).readmitted_patients < MIN_PATIENTS:
        return False
    low_a, high_a = wilson(level.readmitted, level.stays)
    low_b, high_b = wilson(rest.readmitted, rest.stays)
    return high_a < low_b or high_b < low_a


def shortlist(rows: Iterable[tuple[str, bool]]) -> list[str]:
    """Signals known at discharge with at least one separating level."""
    return sorted({signal for signal, sep in rows
                   if sep and signal not in NOT_AT_DISCHARGE
                   and not signal.startswith(LEAK_PREFIXES)})


def verdict(shortlisted: list[str]) -> str:
    return "GO" if len(shortlisted) >= MIN_SIGNALS else "NO-GO"


def _small(side: Side) -> bool:
    # Zero readmissions is published: it points at no one.
    return side.stays < SUPPRESS_BELOW or 0 < side.readmitted < SUPPRESS_BELOW


def level_row(signal: str, level: str, side: Side, rest: Side) -> dict:
    """One published row; any 1-10 count on either side hides every count and rate (D66)."""
    row = {"signal": signal, "chapter": SIGNALS[signal], "level": level,
           "at_discharge": signal not in NOT_AT_DISCHARGE,
           "separates": separates(side, rest),
           "suppressed": _small(side) or _small(rest)}
    if row["suppressed"]:
        return row
    low, high = wilson(side.readmitted, side.stays)
    rest_low, rest_high = wilson(rest.readmitted, rest.stays)
    return row | {"index_stays": side.stays, "readmitted": side.readmitted,
                  "rate": side.rate, "low": low, "high": high,
                  "rest_stays": rest.stays, "rest_readmitted": rest.readmitted,
                  "rest_rate": rest.rate, "rest_low": rest_low, "rest_high": rest_high}


def hidden_sum(rows: list[dict]) -> Side | None:
    """What a signal's hidden levels hold together, by subtraction; None if nothing is shown."""
    shown = [row for row in rows if not row["suppressed"]]
    if not shown:
        return None
    stays = shown[0]["index_stays"] + shown[0]["rest_stays"]
    readmitted = shown[0]["readmitted"] + shown[0]["rest_readmitted"]
    return Side(stays - sum(row["index_stays"] for row in shown),
                readmitted - sum(row["readmitted"] for row in shown), 0)


def complete_suppression(rows: list[dict]) -> list[dict]:
    """Hide more levels until the hidden ones hold 0 or 11+ together, never just one (D66, D79)."""
    out = list(rows)
    for signal in {row["signal"] for row in out}:
        mine = [i for i, row in enumerate(out) if row["signal"] == signal]
        while True:
            shown = [i for i in mine if not out[i]["suppressed"]]
            left = hidden_sum([out[i] for i in mine])
            if left is None or not (len(mine) - len(shown) == 1 or
                                    (left.stays and _small(left))):
                break
            pick = min(shown, key=lambda i: (out[i]["level"] != "other",
                                             out[i]["readmitted"] == 0,
                                             out[i]["readmitted"], out[i]["index_stays"]))
            out[pick] = {k: out[pick][k] for k in
                         ("signal", "chapter", "level", "at_discharge", "separates")} | {
                         "suppressed": True}
    return out
