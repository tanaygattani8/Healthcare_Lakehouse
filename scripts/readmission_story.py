"""Chapter 5's rule (spec §5), fixed before any number was looked at.

Pure Python: publish_snapshot feeds it counts from the metric views, and
it decides, per signal level, whether readmitted stays separate from the
rest, and whether phase 6 is GO.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

MIN_STAYS = 30          # index stays on each side of a comparison
MIN_PATIENTS = 10       # distinct readmitted patients on the higher-rate side
MIN_SIGNALS = 2         # shortlisted signals needed for GO
SUPPRESS_BELOW = 11     # index stays; a smaller cell is not published
Z = 1.96                # 95%

# Each dimension of metrics.readmission, and the chapter it belongs to (spec §2).
SIGNALS = {
    "admit_year": 1,
    "age_band": 2, "gender": 2, "has_diabetes": 2, "has_hypertension": 2,
    "has_cardiovascular_disease": 2, "above_median_conditions": 2,
    "admit_reason_group": 3, "is_planned": 3, "above_median_length_of_stay": 3,
    "prior_stays_12m_band": 3, "prior_emergency_12m_band": 3, "post_followup_7d": 3,
}
# Shown in the story, never shortlisted: a calendar dimension, and a fact
# known only after discharge.
NOT_AT_DISCHARGE = {"admit_year", "post_followup_7d"}


@dataclass(frozen=True)
class Side:
    stays: int
    readmitted: int
    readmitted_patients: int

    @property
    def rate(self) -> float:
        return self.readmitted / self.stays if self.stays else 0.0


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    """The Wilson interval for k of n. Unlike p ± z·se it stays inside 0-1,
    which matters for a level with few or no readmissions."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def separates(level: Side, rest: Side) -> bool:
    """Spec §5: enough stays on both sides, enough different people behind
    the higher rate, and 95% intervals that do not overlap."""
    if min(level.stays, rest.stays) < MIN_STAYS:
        return False
    if max(level, rest, key=lambda side: side.rate).readmitted_patients < MIN_PATIENTS:
        return False
    low_a, high_a = wilson(level.readmitted, level.stays)
    low_b, high_b = wilson(rest.readmitted, rest.stays)
    return high_a < low_b or high_b < low_a


def shortlist(rows: Iterable[tuple[str, bool]]) -> list[str]:
    """Signals known at discharge with at least one level that separates.
    rows: (signal, separates), one per level."""
    return sorted({signal for signal, sep in rows if sep and signal not in NOT_AT_DISCHARGE})


def verdict(shortlisted: list[str]) -> str:
    return "GO" if len(shortlisted) >= MIN_SIGNALS else "NO-GO"


def _small(side: Side) -> bool:
    # Zero readmissions is published: it points at no one.
    return side.stays < SUPPRESS_BELOW or 0 < side.readmitted < SUPPRESS_BELOW


def level_row(signal: str, level: str, side: Side, rest: Side) -> dict:
    """One published row. Whether the level separates is decided on the real
    counts; then a level whose stays or readmissions, or the rest's, number
    1-10 loses every count and rate (D66). Rates go too, since rate × stays
    gives the count back. Patient counts are never published (plan P-e)."""
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


def complete_suppression(rows: list[dict]) -> list[dict]:
    """A signal's levels add up to the published totals, so one hidden level
    is found by subtraction. Where a signal has exactly one, hide its
    smallest published level too, preferring one with readmissions (D66)."""
    out = list(rows)
    for signal in {row["signal"] for row in out}:
        mine = [i for i, row in enumerate(out) if row["signal"] == signal]
        shown = [i for i in mine if not out[i]["suppressed"]]
        if len(mine) - len(shown) == 1 and shown:
            pick = min(shown, key=lambda i: (out[i]["readmitted"] == 0,
                                             out[i]["readmitted"], out[i]["index_stays"]))
            out[pick] = {k: out[pick][k] for k in
                         ("signal", "chapter", "level", "at_discharge", "separates")} | {
                         "suppressed": True}
    return out
