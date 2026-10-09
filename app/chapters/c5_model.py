"""Chapter 5: can a model beat one rule? Comparison and drift (D80); 1-10 recalls hidden."""

import altair as alt
import pandas as pd
import streamlit as st
import ui

POPULATIONS = {"all": "Every index stay", "no_bypass": "Without bypass-surgery stays"}
SCORERS = {"base_rate": "Base rate: flag at random", "rule": "One rule: heart disease or stroke",
           "model": "The model (champion)"}
FEATURES = {"admit_reason": "Admit reason", "conditions_at_admit": "Conditions at admission",
            "age_at_admit": "Age", "has_cardiovascular_disease": "Heart disease or stroke",
            "days_since_last_discharge": "Days since the last discharge",
            "has_hypertension": "Hypertension", "has_diabetes": "Diabetes",
            "length_of_stay_days": "Length of stay", "encounters_in_stay": "Encounters in the stay",
            "had_bypass_surgery": "Bypass surgery",
            "prior_emergency_12m": "Emergency visits, year before",
            "is_planned": "Planned admission", "gender": "Gender",
            "prior_stays_12m": "Hospital stays, year before",
            "arrived_via_emergency": "Arrived through emergency"}
# Yes/no features are judged by their rate, not PSI (D71): drawn hollow.
YES_NO = ("has_", "is_", "had_", "arrived_")

results = ui.snapshot("model_results")
drift = ui.snapshot("model_drift")
history = ui.snapshot("retrain_history")
live = history[history["mode"] == "live"].iloc[-1]
p = ui.palette()
models = results[(results["scorer"] == "model") & (results["patients"] == "all")]
top = models[models["population"] == "all"].iloc[0]

ui.chapter(5, "The readmission model", "Can a model beat one rule?",
           "Trained on stays from 2000 to 2019 and judged on 2020-2026, a model was asked to "
           "beat one rule, \"heart disease or stroke on the admit day\". Judged where it would "
           "run, at its own cutoff against the rule cut to as many alerts, it caught "
           f"{100 * top.cut_mid:.1f} points more of the readmissions, "
           + {"beats": "and the whole interval clears zero: it beats the rule.",
              "no better": "but not enough to rule out luck.",
              "too few to judge": "on too few readmissions to judge."}[top.cutoff_verdict])

COMPARISONS = {"cut": "at its cutoff", "diff": "at the rule's count"}
SHORT = {"all": "All stays", "no_bypass": "No bypass"}
gap = pd.concat([models.assign(comparison=label, low=models[f"{key}_low"],
                               mid=models[f"{key}_mid"], high=models[f"{key}_high"],
                               verdict=models["cutoff_verdict" if key == "cut"
                                              else "model_verdict"])
                 for key, label in COMPARISONS.items()])
gap = gap.sort_values("population", kind="stable")
gap["row"] = gap["population"].map(SHORT) + " · " + gap["comparison"]

main, side = ui.section()
with main:
    ui.numbers([(f"{100 * top.cut_mid:+.1f}", "points of readmissions caught, model minus rule, "
                                               "at the model's cutoff"),
                (f"{100 * top.cut_low:+.1f} … {100 * top.cut_high:+.1f}",
                 "95% interval, patients resampled")])
    for row in models.itertuples():
        ui.stamp(f"{POPULATIONS[row.population]} · {row.cutoff_verdict}")
    pts = alt.Chart(gap).encode(
        y=alt.Y("row:N", title=None, sort=list(gap["row"])),
        tooltip=["row:N", "verdict:N",
                 alt.Tooltip("mid:Q", title="median", format="+.1%"),
                 alt.Tooltip("low:Q", title="95% from", format="+.1%"),
                 alt.Tooltip("high:Q", title="95% to", format="+.1%")])
    span = pts.mark_rule(strokeWidth=3, color=p["series"][0]).encode(
        x=alt.X("low:Q", title="model minus rule, points caught",
                axis=alt.Axis(format="+.0%")), x2="high:Q")
    mid = pts.mark_point(filled=True, size=110, color=p["series"][0]).encode(x="mid:Q")
    verdict = pts.mark_text(align="left", dx=10, dy=-12, fontSize=11).encode(
        x="low:Q", text="verdict:N", color=alt.value(p["muted"]))
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(
        color=p["accent"], strokeDash=[4, 4]).encode(x="x:Q")
    ui.figure((zero + span + mid + verdict).properties(height=60 * len(gap)), "5.1",
              "The model's lead over the rule, median and 95% interval, resampling patients, "
              "measured two ways. At its cutoff: the model flags what its training cutoff "
              "flags, and the rule, which is yes/no, is cut at random to as many alerts. At the "
              "rule's count: both flag as many as the rule does, which no deployment would. It "
              "beats the rule only if the whole interval is right of zero (dashed). The "
              "recalls themselves are hidden: each rests on 1-10 readmissions caught or missed.")
with side:
    champion = (f"v{live.new_version}, the same model with a new cutoff set by chapter 6's "
                "retraining loop" if pd.notna(live.new_version) else
                f"still v{live.champion_version}: the live retraining run changed nothing")
    ui.notes("Synthetic data: the model's absolute score means nothing here; only the "
             "comparison with the rule does.",
             "It beats the rule only if the whole 95% interval is above zero, and under 30 "
             "readmissions is too few to judge. Both fixed before any number was seen. "
             "<i>D71</i>",
             "First published judged at the rule's count only, as \"no better\". An audit "
             "pointed out no deployment runs there; and training reached back to 1915, so "
             "drift was there on day one. Training now starts in 2000. <i>D80</i>",
             f"The live champion is {champion}. <i>D75, D80</i>",
             "Without bypass surgery is an experiment, not a product: 61 readmissions in "
             "9,891 stays is 0.62%, under the 1% line phase 1's gate set before any model "
             "(the gate says pivot there; on every stay, 1.31%, it says proceed). It is "
             "scored but never retrained. <i>D81</i>")

ui.heading("Drift", "Has the data moved since training?")
main, side = ui.section()
with main:
    features = drift[drift["drift_check"] == "feature"].assign(
        kind=lambda d: d["subject"].str.startswith(YES_NO).map(
            {True: "yes/no: judged by its rate", False: "judged by PSI"}),
        subject=lambda d: d["subject"].map(FEATURES).fillna(d["subject"]))
    status = alt.Color("status:N", legend=None,
                       scale=alt.Scale(domain=["stable", "watch", "shifted"],
                                       range=[p["muted"], p["series"][1], p["series"][0]]))
    dots = alt.Chart(features).mark_point(size=70, strokeWidth=2).encode(
        x=alt.X("value:Q", title="population stability index (PSI)",
                scale=alt.Scale(domain=[0, float(features["value"].max()) * 1.2])),
        y=alt.Y("subject:N", title=None, sort="-x"),
        color=status,
        fill=alt.condition("datum.kind == 'judged by PSI'", status, alt.value("transparent")),
        tooltip=["subject:N", alt.Tooltip("value:Q", title="PSI", format=".3f"), "status:N",
                 "kind:N"])
    tags = dots.mark_text(align="left", dx=9, fontSize=10).encode(
        text="status:N", color=alt.value(p["muted"]), fill=alt.value(p["muted"]))
    rules = alt.Chart(pd.DataFrame({"x": [0.1, 0.25]})).mark_rule(
        color=p["rule"], strokeDash=[3, 3]).encode(x="x:Q")
    ui.figure((rules + dots + tags).properties(height=24 * len(features)), "5.2",
              "Each feature's shift from training to 2020-2026. Under 0.1 stable, 0.1-0.25 "
              "watch, over 0.25 shifted; every point is labelled with its status. Hollow points "
              "are yes/no features, judged by their rate, so one can read shifted at a low PSI.")
    flags = drift[drift["drift_check"] == "flag_rate"].assign(
        population=lambda d: d["subject"].map(POPULATIONS))
    band = alt.Chart(flags).mark_area(opacity=0.18).encode(
        x=alt.X("period:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("low:Q", title="stays flagged", axis=alt.Axis(format="%"),
                scale=alt.Scale(zero=False)), y2="high:Q",
        color=alt.Color("population:N", scale=alt.Scale(range=list(p["series"])),
                        legend=alt.Legend(labelLimit=0)))
    line = alt.Chart(flags).mark_line(point=True, strokeWidth=2).encode(
        x="period:O", y="value:Q", color="population:N",
        tooltip=["population:N", "period:O", alt.Tooltip("value:Q", format=".1%")])
    ui.figure((band + line).properties(height=240), "5.3",
              "Share of stays each live champion flags per year, with its 95% interval. Every "
              "cutoff is set to flag the workload budget, the rule's rate in training; a move "
              "away from it is drift, not an error. "
              + (f"For every stay the champion is v{live.new_version}, whose cutoff chapter 6's "
                 "live run reset on the latest year, so earlier years can read off budget. "
                 "Judged on its own windows (E73)." if pd.notna(live.new_version) else
                 "Chapter 6 picks this up."))
with side:
    ui.notes("A true/false feature is judged by its rate, not PSI: PSI barely moves on two "
             "values. Heart disease went from 24.9% to 35.4% of stays at a PSI of 0.05.",
             "2020-2026 patients are older and carry more chronic disease, and COVID-19 arrives "
             "as an admit reason training never saw.")

with ui.method("Every scorer, the per-patient breakdown, and the readmission rate"):
    every = results[results["patients"] == "all"]
    ui.table(pd.DataFrame({
        "population": every["population"].map(POPULATIONS),
        "scored by": every["scorer"].map(SCORERS),
        "caught %": every["recall"].map(lambda v: "hidden" if pd.isna(v) else f"{100 * v:.1f}"),
        "average precision": every["avg_precision"].round(3),
        "cross-validated": every["cv_avg_precision"].round(3),
        "Brier": every["brier"].round(4)}))
    breakdown = results[(results["patients"] != "all") & (results["scorer"] == "model")]
    st.caption("By patient, verdict only (some hold 1-10 readmissions): "
               + "; ".join(f"{POPULATIONS[r.population].lower()}, {r.patients}: {r.model_verdict}"
                           for r in breakdown.itertuples()) + ".")
    rate = drift[drift["drift_check"] == "readmission_rate"]
    ui.table(pd.DataFrame({
        "population": rate["subject"].map(POPULATIONS), "period": rate["period"],
        "readmission rate %": (100 * rate["value"]).round(2),
        "95% interval %": [f"{100 * lo:.2f}–{100 * hi:.2f}"
                           for lo, hi in zip(rate["low"], rate["high"], strict=True)],
        "status": rate["status"]}))

ui.pager(5)
