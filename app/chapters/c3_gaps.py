"""Chapter 3: care gaps, three HEDIS-style measures built in gold."""

import altair as alt
import ui

MEASURES = {"bp_control": "Blood pressure under 140/90",
            "diabetes_hba1c": "Diabetics with an HbA1c test",
            "statin_therapy": "Heart patients on a statin"}

gaps = ui.snapshot("gold_care_gap")
gaps["measure"] = gaps["measure"].map(MEASURES)
gaps["met_rate"] = gaps["met"] / gaps["eligible"]
year = int(gaps["measure_year"].iloc[0])
p = ui.palette()

ui.chapter(3, "Quality measures", "Care gaps",
           f"Three quality measures for {year}, built in the gold layer the way a health plan "
           "would: who is in the group, who is excluded, who met the measure, who has a gap. "
           "The interesting part is not the rates. It is knowing which of them the data "
           "generator decided.")

main, side = ui.section()
with main:
    ui.numbers([(f"{100 * r.met_rate:.1f}%", r.measure) for r in gaps.itertuples()])
    track = alt.Chart(gaps).mark_bar(height=16, color=p["faint"]).encode(
        x=alt.X("one:Q", title="share of the eligible group that met the measure",
                axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("measure:N", title=None, sort="-x")).transform_calculate(one="1")
    met = alt.Chart(gaps).mark_bar(height=16, color=p["series"][0]).encode(
        x="met_rate:Q", y=alt.Y("measure:N", sort="-x"),
        tooltip=["measure:N", alt.Tooltip("eligible:Q", format=","),
                 alt.Tooltip("met:Q", format=","), alt.Tooltip("gaps:Q", format=","),
                 alt.Tooltip("met_rate:Q", title="met", format=".1%")])
    label = met.mark_text(align="left", dx=6, fontSize=11).encode(
        text=alt.Text("met_rate:Q", format=".1%"))
    ui.figure((track + met + label).properties(height=150), "3.1",
              "Met (filled) against the whole eligible group (track). The unfilled part of "
              "each track is that measure's care gap.")
with side:
    ui.notes("Read these as the generator's rules, not as a finding about care. Synthea "
             "prescribes a statin as part of the heart treatment it simulates, so the statin "
             "rate says how the data was made.",
             "The other two land where real-world rates do, which is also what the generator "
             "was tuned to.",
             f"Only people alive on 1 January {year} are in a measure's group. <i>D59</i>")

with ui.method("The measure table: denominator, exclusions, gaps"):
    ui.table(gaps[["measure", "in_denominator", "excl_age", "excl_died", "excl_hospice",
                   "eligible", "met", "gaps"]].sort_values("measure"))

ui.pager(3)
