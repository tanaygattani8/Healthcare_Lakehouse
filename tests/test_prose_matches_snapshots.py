"""The hand-typed home-page findings must match the snapshots (D80, D81)."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "app/ui.py").read_text(encoding="utf-8")


def snapshot(name: str) -> pd.DataFrame:
    return pd.read_parquet(ROOT / "snapshots" / f"{name}.parquet")


def test_chapter_4s_line_matches_the_story_totals():
    t = snapshot("story_totals").iloc[0]
    line = (f"{int(t.readmitted)} of {int(t.index_stays):,} stays, "
            f"{100 * t.readmitted / t.index_stays:.2f}%")
    assert line in UI, line


def test_chapter_5s_line_matches_the_model_results():
    r = snapshot("model_results").query(
        "population == 'all' and scorer == 'model' and patients == 'all'").iloc[0]
    line = (f"+{100 * r.cut_mid:.1f} points caught, interval {100 * r.cut_low:+.1f} "
            f"to {100 * r.cut_high:+.1f}: it {r.cutoff_verdict} the rule")
    assert line in UI, line
