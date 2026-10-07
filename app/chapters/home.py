"""The home page: the lakehouse as a transit map. Each station is a chapter,
carries its headline number from the snapshots, and opens its page."""

import streamlit as st
import ui

ui.style()
p = ui.palette()

counts = ui.snapshot("bronze_counts")
quarantined = int(counts.loc[counts["layer"] == "quarantine", "rows"].sum())
modelled = int(counts.loc[counts["layer"] == "silver", "rows"].sum()) + quarantined
patients = int(counts.query("layer == 'bronze' and entity == 'patients'")["rows"].sum())
kanon = ui.snapshot("deid_kanon")
released = kanon[(kanon["version"] == "released") & (kanon["people"] > 0)]["k"]
totals = ui.snapshot("story_totals").iloc[0]
results = ui.snapshot("model_results")
verdict = results.query("population == 'all' and scorer == 'model' and patients == 'all'")
history = ui.snapshot("retrain_history")
live = history[history["mode"] == "live"].iloc[-1]

# Station: (chapter, x, y, label anchor, line colour, number on the map).
STATIONS = [
    (1, 210, 112, "below", "bronze", f"{quarantined:,} of {modelled / 1e6:.1f}M quarantined"),
    (2, 395, 46, "above", "silver",
     "k ≥ 5 released" if not set(released) & {"1", "2", "3", "4"} else "k < 5 left"),
    (3, 470, 112, "below", "gold", f"{len(ui.snapshot('gold_care_gap'))} measures"),
    (4, 545, 172, "below", "gold",
     f"{100 * totals.readmitted / totals.index_stays:.2f}% come back"),
    (5, 640, 112, "below", "gold", verdict["model_verdict"].iloc[0]),
    (6, 740, 46, "above", "gold", f"live v{live.new_version or live.champion_version}"),
]
LABELS = {n: (path.split("_", 1)[1][:-3], short) for n, path, short, _, _ in ui.CHAPTERS}


def station(n, x, y, where, colour, number):
    slug, short = LABELS[n]
    dy = (-30, -14) if where == "above" else (30, 46)
    return (f'<a href="{slug}" target="_self" aria-label="Chapter {n}: {ui.esc(short)}">'
            f'<circle cx="{x}" cy="{y}" r="11" fill="{p["bg"]}" stroke="{p[colour]}" '
            f'stroke-width="4"/>'
            f'<text class="st" x="{x}" y="{y + dy[0]}" text-anchor="middle" font-size="13" '
            f'font-weight="600" fill="{p["ink"]}">{n} · {ui.esc(short)}</text>'
            f'<text x="{x}" y="{y + dy[1]}" text-anchor="middle" font-size="11" '
            f'font-family="JetBrains Mono, monospace" fill="{p["muted"]}">'
            f'{ui.esc(number)}</text></a>')


track = (
    f'<line x1="40" y1="112" x2="210" y2="112" stroke="{p["bronze"]}" stroke-width="7" '
    f'stroke-linecap="round"/>'
    f'<line x1="210" y1="112" x2="330" y2="112" stroke="{p["silver"]}" stroke-width="7"/>'
    f'<line x1="330" y1="112" x2="700" y2="112" stroke="{p["gold"]}" stroke-width="7"/>'
    f'<path d="M290 112 Q 310 46 360 46 L 395 46" stroke="{p["silver"]}" stroke-width="5" '
    f'fill="none"/>'
    f'<path d="M500 112 Q 515 172 545 172" stroke="{p["gold"]}" stroke-width="5" fill="none"/>'
    f'<path d="M680 112 Q 700 46 740 46" stroke="{p["gold"]}" stroke-width="5" fill="none"/>'
)
ends = (
    f'<circle cx="40" cy="112" r="9" fill="{p["bg"]}" stroke="{p["bronze"]}" stroke-width="4"/>'
    f'<text x="40" y="142" text-anchor="middle" font-size="12" fill="{p["muted"]}">Synthea</text>'
    f'<circle cx="330" cy="112" r="9" fill="{p["bg"]}" stroke="{p["silver"]}" stroke-width="4"/>'
    f'<text x="330" y="142" text-anchor="middle" font-size="12" fill="{p["muted"]}">Gold</text>'
    f'<circle cx="700" cy="112" r="9" fill="{p["bg"]}" stroke="{p["ink"]}" stroke-width="4"/>'
    f'<text x="716" y="116" font-size="12" fill="{p["muted"]}">Airflow</text>'
)
svg = (f'<svg class="lh-map" viewBox="0 0 800 225" width="100%" role="img" '
       f'aria-label="The pipeline as a map: Synthea to bronze and silver, a branch to '
       f'de-identification, gold, then care gaps, the readmission story, the model and the '
       f'retraining loop" font-family="Inter, sans-serif">{track}{ends}'
       f'{"".join(station(*s) for s in STATIONS)}</svg>')

toc = "".join(
    f'<a href="{path.split("_", 1)[1][:-3]}" target="_self"><div class="n">{n:02d}</div>'
    f'<div class="t">{ui.esc(title)}</div><div class="f">{ui.esc(line)}</div></a>'
    for n, path, _, title, line in ui.CHAPTERS)

st.html(f"""
<div class="lh-kicker">{patients:,} synthetic patients · Databricks Free Edition</div>
<h1 class="lh-title">Healthcare Lakehouse</h1>
<div class="lh-stand">One lakehouse, from raw synthetic health records to a model that was
replayed for six years before it was trusted. Every station below is a chapter, and every
number on the line is the one that chapter answers. Follow the line.</div>""")
# st.html's sanitiser drops SVG; markdown with raw HTML keeps it, links included.
st.markdown(svg, unsafe_allow_html=True)
st.html(f'<div class="lh-toc">{toc}</div>')
ui.colophon()
