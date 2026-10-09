"""Hand-typed findings (home page, chapter 4) must match the snapshots (D80, D81)."""
import ast
import re
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


def chapter_4_findings() -> str:
    tree = ast.parse((ROOT / "app/chapters/c4_story.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == "FINDINGS")
    return " ".join(ast.literal_eval(node.value).values())


def test_chapter_4s_findings_match_the_story_snapshots():
    text = chapter_4_findings()
    t = snapshot("story_totals").iloc[0]
    levels = snapshot("story_levels")
    rates = {f"{100 * v:.2f}%" for v in levels[["rate", "rest_rate"]].stack()}
    rates.add(f"{100 * t.readmitted / t.index_stays:.2f}%")
    # 12.31%: the rate before D64 and D68, which no snapshot holds.
    quoted = set(re.findall(r"\d+\.\d\d%", text)) - {"12.31%"}
    assert quoted <= rates, quoted - rates
    counts = snapshot("story_verdict").iloc[0]
    for number in (f"{int(t.readmitted)} of {int(t.index_stays):,}",
                   f"from {int(t.readmitted_patients)} different",
                   f"{int(counts.shortlisted)} signals"):
        assert number in text, number
