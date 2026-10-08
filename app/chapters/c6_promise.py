"""Chapter 6: the retraining loop (phase 9, D75; rerun in D80), replayed one
year at a time and then run once for real. Rates and verdicts only."""

import altair as alt
import pandas as pd
import ui

h = ui.snapshot("retrain_history").copy()
p = ui.palette()
budget = float(h["target"].iloc[0])
live = h[h["mode"] == "live"].iloc[-1]
h["cursor"] = ["live" if m == "live" else f"{d:%Y}" for d, m in zip(h["as_of"], h["mode"],
                                                                     strict=True)]
h["checks"] = [f"live: {d - pd.DateOffset(years=1):%b %Y}–{d - pd.DateOffset(days=1):%b %Y}"
               if m == "live" else f"checks {d.year - 1}"
               for d, m in zip(h["as_of"], h["mode"], strict=True)]
order = list(h["cursor"])
# Every layer shares one y scale; points would otherwise pull it down to zero.
Y = alt.Scale(domain=[0.15, 0.40], zero=False)

ui.chapter(6, "Retraining on drift", "The model keeps its promise",
           f"The model's cutoff was set to flag {100 * budget:.1f}% of stays, the review "
           "workload the rule asked of nurses. Then the patients changed. The data never "
           "changes, so a date cursor stands in for time: each yearly run is told \"today is "
           "1 January\" and sees only what was known then. Six years were replayed in a "
           "sandbox before the same rule was allowed to touch the live model.")

main, side = ui.section()
with main:
    first = h.iloc[0]
    ui.numbers([(f"{100 * budget:.1f}%", "the workload budget: stays flagged for review"),
                (f"{100 * first.champion_rate:.1f}%", f"flagged in {first.as_of.year - 1} by "
                                                       "the model trained on 2000-2019"),
                (f"{100 * live.cutoff_rate:.1f}%", f"flagged after the live run's new cutoff, "
                                                   f"now model v{live.new_version}")])
    ui.stamp(f"Live · {live.outcome} → v{live.new_version}")

    champ = alt.Chart(h).encode(
        x=alt.X("cursor:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
        tooltip=[alt.Tooltip("cursor:N", title="run"), alt.Tooltip("checks:N", title="window"),
                 alt.Tooltip("champion_rate:Q", title="champion flags", format=".1%"),
                 alt.Tooltip("outcome:N")])
    whisker = champ.mark_rule(strokeWidth=2, color=p["muted"], opacity=0.75).encode(
        y=alt.Y("champion_low:Q", title="stays flagged", axis=alt.Axis(format="%"), scale=Y),
        y2="champion_high:Q")
    dot = champ.mark_point(filled=True, size=90, color=p["ink"]).encode(
        y=alt.Y("champion_rate:Q", scale=Y))
    tried = (h.melt(id_vars=["cursor"], value_vars=["cutoff_rate", "retrain_rate"],
                    var_name="challenger", value_name="rate").dropna()
              .replace({"cutoff_rate": "new cutoff", "retrain_rate": "retrained model"}))
    challengers = alt.Chart(tried).mark_point(size=80, strokeWidth=2.5).encode(
        x=alt.X("cursor:N", sort=order), y=alt.Y("rate:Q", scale=Y),
        color=alt.Color("challenger:N", scale=alt.Scale(range=list(p["series"]))),
        shape=alt.Shape("challenger:N", scale=alt.Scale(range=["diamond", "triangle-up"])),
        xOffset=alt.XOffset("challenger:N"),
        tooltip=["cursor:N", "challenger:N", alt.Tooltip("rate:Q", format=".1%")])
    line = alt.Chart(pd.DataFrame({"y": [budget]})).mark_rule(
        color=p["accent"], strokeDash=[5, 4], strokeWidth=1.5).encode(y=alt.Y("y:Q", scale=Y))
    ui.figure((line + whisker + dot + challengers).properties(height=330), "6.1",
              "Each run's champion (dot, with its 95% interval) on the year before it. A run "
              f"fires when the interval leaves the {100 * budget:.1f}% budget (dashed); then two "
              "challengers are judged "
              "on the same year: a new cutoff on the same model (diamond) and a retrained model "
              "(triangle). The last run, live, is 15 July 2026, on mid-2025 to mid-2026.")
with side:
    ui.notes("It judges workload, not accuracy. At about 5 readmissions a year, no one-year "
             "window can show one model ranks better than another.",
             "The simpler change wins when both pass: a new cutoff before a new model.",
             "Each run sees only stays admitted before its date, and outcomes known 30 days "
             "after discharge. <i>D75</i>")

ui.heading("What six years showed", "Three findings, and three limits")
main, side = ui.section()
with main:
    ui.finding("<b>2020 broke the pattern.</b> A cutoff learned on 2019 did not fit 2020: "
               "the first run fired and both challengers failed. 2020 is also when COVID-19 "
               "arrives as an admit reason, in 7% of stays. On the first run, trained back to "
               "1915, 2020 looked like a trend continuing (D75); that was the old window.")
    ui.finding("<b>A new cutoff was enough whenever anything was.</b> Each time a fix passed, "
               "both had passed and the simpler one won; in 2020 both failed alike. A retrained "
               "model never caught what a new cutoff missed.")
    ui.finding("<b>Each fix lasts about two years.</b> The flag rate creeps up a point or so a "
               "year, and the trigger, about ±4.5 points wide at 350 stays, fires on the third "
               "year. It fired in the 2024 and 2026 runs, and again live.")
with side:
    ui.notes("Every decision rests on about 350 stays.",
             "The live run starts from the live champion, not from the sandbox's: the replays' "
             "promotions never touch the live model. <i>D75</i>",
             "First run on a model trained back to 1915, kept as ml.retrain_history_d75; "
             "rerun on the 2000-2019 model, and retraining now uses the 20 years before each "
             "run. <i>D80</i>",
             "Not built, and handed on: a cutoff set on recent months, and a trend test across "
             "runs.")

with ui.method("Every run, as recorded in ml.retrain_history"):
    table = h.assign(**{
        "champion %": (100 * h["champion_rate"]).round(1),
        "95% interval": [f"{100 * lo:.1f}–{100 * hi:.1f}"
                         for lo, hi in zip(h["champion_low"], h["champion_high"], strict=True)],
        "new cutoff %": (100 * h["cutoff_rate"]).round(1),
        "retrain %": (100 * h["retrain_rate"]).round(1)})
    ui.table(table[["cursor", "mode", "champion_version", "check_stays", "champion %",
                    "95% interval", "triggered", "new cutoff %", "cutoff_workload",
                    "retrain %", "retrain_workload", "retrain_ranking", "outcome",
                    "new_version", "shifted_features"]])

ui.pager(6)
