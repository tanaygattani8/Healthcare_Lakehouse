"""The app's design kit: "layer metals" (README, What the app looks like).

Pages are short scripts that read like the paper: chapter(), then for each
section a reading column and a margin (section()), numbers, a figure, a
verdict stamp. Everything Streamlit does not draw itself is a few lines of
HTML here, styled by one stylesheet, in the palette .streamlit/config.toml
also uses. Snapshots are the only data (README, Architecture notes).
"""

from __future__ import annotations

import html
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

SNAPSHOTS = Path(__file__).resolve().parent.parent / "snapshots"

# The same colours as .streamlit/config.toml, plus what only the kit draws.
# Chart pairs (series) were checked with the dataviz palette validator in both
# modes: lightness band, chroma, colour-blind and normal-vision separation.
PALETTES = {
    "light": {"bg": "#F6F4EF", "surface": "#EDE9E0", "ink": "#16181D", "muted": "#5A606B",
              "rule": "#DAD5CA", "accent": "#8A5A1F", "faint": "#B7B1A5",
              "bronze": "#A0612E", "silver": "#77808C", "gold": "#977511",
              "series": ("#9A5A12", "#3A68A8")},
    "dark": {"bg": "#0E1116", "surface": "#161A21", "ink": "#E8EAED", "muted": "#9AA2AE",
             "rule": "#262B33", "accent": "#D4A72C", "faint": "#3A404A",
             "bronze": "#C9844A", "silver": "#A8B0BB", "gold": "#D4A72C",
             "series": ("#B8861A", "#5B8FDB")},
}

# Every chapter, in reading order: number, page file, short label for the top
# bar, title, and its one-line finding for the home page.
CHAPTERS = [
    (1, "chapters/c1_data.py", "Data", "The data arrives",
     "Every raw row lands; the ones that break a rule are kept, not dropped."),
    (2, "chapters/c2_hiding.py", "Hiding", "Hiding the patients",
     "Four programs against an answer sheet; Safe Harbor alone left people unique."),
    (3, "chapters/c3_gaps.py", "Gaps", "Care gaps",
     "Three quality measures, read as the generator's rules, not as care."),
    (4, "chapters/c4_story.py", "Who comes back", "Who comes back",
     "140 of 10,724 stays, 1.31%, and most of them one bypass-surgery rule."),
    (5, "chapters/c5_model.py", "The model", "Can a model beat one rule?",
     "+12.2 points caught, interval -3.0 to +29.0: no better."),
    (6, "chapters/c6_promise.py", "The promise", "The model keeps its promise",
     "Six years replayed: moving the cutoff was always enough, until it lagged."),
    (7, "chapters/c7_operations.py", "Operations", "Running the network",
     "Phase 8's dashboard for an operations director: twelve months against the twelve before."),
]


def mode() -> str:
    theme = getattr(st.context, "theme", None)
    return "dark" if theme is not None and theme.type == "dark" else "light"


def palette() -> dict:
    return PALETTES[mode()]


def esc(text) -> str:
    return html.escape(str(text))


def snapshot(name: str) -> pd.DataFrame:
    path = SNAPSHOTS / f"{name}.parquet"
    if not path.exists():
        st.error(f"No `{name}` snapshot. Run `python -m scripts.publish_snapshot`.")
        st.stop()
    return pd.read_parquet(path)


def style() -> None:
    """The stylesheet, once per run, in the viewer's light or dark palette."""
    p = palette()
    root = (f":root {{ --ink:{p['ink']}; --muted:{p['muted']}; --rule:{p['rule']}; "
            f"--accent:{p['accent']}; --surface:{p['surface']}; --bg:{p['bg']}; "
            f"--faint:{p['faint']}; }}")
    css = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")
    # The palette goes after the file: a stylesheet's @import must come first.
    st.html(f"<style>{css}\n{root}</style>")


def chapter(n: int, kicker: str, title: str, standfirst: str, wide: bool = False) -> None:
    style()
    if wide:
        # A dashboard's tables and charts need more than the paper's reading width.
        st.html('<style>[data-testid="stMainBlockContainer"] { max-width: 1320px; }</style>')
    st.html(f'<div class="lh-kicker">Chapter {n:02d} · {esc(kicker)}</div>'
            f'<h1 class="lh-title">{esc(title)}</h1>'
            f'<div class="lh-stand">{standfirst}</div>')
    strip(n)


def heading(label: str, title: str) -> None:
    st.html(f'<h2 class="lh-h2"><small>{esc(label)}</small>{esc(title)}</h2>')


def section():
    """A reading column and its margin. On a phone the margin drops under it."""
    return st.columns([3, 1], gap="large")


def numbers(items: list[tuple[str, ...]]) -> None:
    """Key numbers: (value, label), or (value, label, a comparison line)."""
    cells = "".join(f'<div class="lh-num"><div class="v">{esc(v)}</div>'
                    f'<div class="l">{esc(label)}</div>'
                    + "".join(f'<div class="s">{esc(x)}</div>' for x in rest) + "</div>"
                    for v, label, *rest in items)
    st.html(f'<div class="lh-nums">{cells}</div>')


def stamp(text: str) -> None:
    st.html(f'<span class="lh-stamp">{esc(text)}</span>')


def finding(text: str) -> None:
    st.html(f'<div class="lh-finding">{text}</div>')


def notes(*items: str, across: bool = False) -> None:
    """Margin notes: the caveats and decision numbers, numbered. `across` lays
    them out side by side under a full-width block instead of down a margin."""
    body = "".join(f"<p><b>{i}</b>{item}</p>" for i, item in enumerate(items, 1))
    st.html(f'<div class="lh-notes{" across" if across else ""}">{body}</div>')


def figure(chart: alt.Chart, number: str, caption: str) -> None:
    st.altair_chart(themed(chart), width="stretch", theme=None)
    st.html(f'<div class="lh-cap"><b>Fig. {esc(number)}</b>&ensp;{caption}</div>')


def table(df: pd.DataFrame, formats: dict[str, str] | None = None, missing: str = "–") -> None:
    """A table in the paper's style: rules, not a grid; numbers right-aligned in
    the mono face. `missing` is what an empty cell reads, e.g. "hidden"."""
    formats = formats or {}
    numeric = {c for c in df.columns
               if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])}

    def cell(column, value) -> str:
        if pd.isna(value):
            # Aligned like the numbers it stands in for.
            return f'<td class="x{" r" if column in numeric else ""}">{esc(missing)}</td>'
        if column not in numeric:
            return f"<td>{esc(value)}</td>"
        spec = formats.get(column, ",.0f" if float(value).is_integer() else ",")
        return f'<td class="r">{esc(format(value, spec))}</td>'

    head = "".join(f'<th{" class=r" if c in numeric else ""}>{esc(c)}</th>' for c in df.columns)
    rows = "".join("<tr>" + "".join(cell(c, v) for c, v in row.items()) + "</tr>"
                   for _, row in df.iterrows())
    st.html(f'<div class="lh-table"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def themed(chart: alt.Chart) -> alt.Chart:
    p = palette()
    return (chart.configure(background="transparent", font="Inter")
            .configure_view(stroke=None)
            .configure_axis(labelColor=p["muted"], titleColor=p["muted"], domainColor=p["rule"],
                            tickColor=p["rule"], gridColor=p["rule"], grid=False, labelFontSize=11,
                            titleFontSize=11, titleFontWeight=400, labelFont="Inter",
                            titleFont="Inter")
            .configure_legend(labelColor=p["muted"], titleColor=p["muted"], labelFont="Inter",
                              titleFont="Inter", orient="top", title=None)
            .configure_header(labelColor=p["ink"], titleColor=p["muted"], labelFont="Inter",
                              labelFontSize=12, labelFontWeight=600, labelAnchor="start")
            .configure_text(font="Inter", color=p["ink"]))


def method(label: str = "Method and full table"):
    return st.expander(label)


def strip(current: int) -> None:
    """The map as a thin line: where this chapter sits in the pipeline."""
    p = palette()
    xs = [10 + i * 112 for i in range(len(CHAPTERS))]
    dots = "".join(
        f'<circle cx="{x}" cy="11" r="{7 if n == current else 5}" '
        f'fill="{p["accent"] if n == current else p["bg"]}" '
        f'stroke="{p["accent"] if n <= current else p["rule"]}" stroke-width="3"/>'
        for n, x in zip(range(1, len(CHAPTERS) + 1), xs, strict=True))
    done = xs[current - 1]
    svg = (f'<svg viewBox="0 0 {xs[-1] + 10} 22" width="100%" height="22" aria-hidden="true" '
           'preserveAspectRatio="xMinYMid meet">'
           f'<line x1="10" y1="11" x2="{xs[-1]}" y2="11" stroke="{p["rule"]}" stroke-width="4"/>'
           f'<line x1="10" y1="11" x2="{done}" y2="11" stroke="{p["accent"]}" stroke-width="4"/>'
           f"{dots}</svg>")
    # st.html's sanitiser drops SVG; markdown with raw HTML keeps it.
    st.markdown(f'<div class="lh-strip">{svg}</div>', unsafe_allow_html=True)


def pager(current: int) -> None:
    st.divider()
    left, right = st.columns(2)
    if current > 1:
        n, path, _, title, _ = CHAPTERS[current - 2]
        left.page_link(path, label=f"← {n:02d} · {title}")
    else:
        left.page_link("chapters/home.py", label="← The map")
    if current < len(CHAPTERS):
        n, path, _, title, _ = CHAPTERS[current]
        right.page_link(path, label=f"{n:02d} · {title} →")
    colophon()


def colophon() -> None:
    st.html('<div class="lh-colophon">Synthetic data from Synthea: no real patients. '
            'Aggregates only, and any group of 1&ndash;10 stays or readmissions is hidden, with '
            'whatever would give it back by subtraction. Built on Databricks Free Edition. '
            # A new tab: GitHub refuses to load inside streamlit.app's frame.
            '<a href="https://github.com/tanaygattani8/Healthcare_Lakehouse" target="_blank" '
            'rel="noopener">The source and the decision log</a>.</div>')
