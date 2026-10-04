from pathlib import Path

import pandas as pd
import streamlit as st

SNAP = Path(__file__).parent.parent.parent / "snapshots"
POPULATIONS = {"all": "Every index stay",
               "no_bypass": "Without stays that had bypass surgery"}
SCORERS = {"base_rate": "Base rate: flag at random",
           "rule": "One rule: heart disease or stroke on the admit day",
           "model": "The model (champion)"}
PATIENTS = {"all": "All patients", "new": "New patients", "returning": "Returning patients"}
STATUS = {"stable": "🟢 stable", "watch": "🟡 watch", "shifted": "🔴 shifted",
          "reference": "reference"}

st.set_page_config(page_title="The readmission model", page_icon="🏥")
st.title("Can a model beat one rule?")
st.caption("Synthetic data from Synthea: the model's absolute performance means nothing "
           "here; only the comparison with the rule does. Aggregates only; a recall built "
           "on 1-10 readmissions caught or missed is hidden.")

paths = {name: SNAP / f"model_{name}.parquet" for name in ("results", "drift")}
if not all(path.exists() for path in paths.values()):
    st.error("No model snapshot. Run `python -m scripts.publish_snapshot`.")
    st.stop()
results = pd.read_parquet(paths["results"])
drift = pd.read_parquet(paths["drift"])

st.header("The verdict")
st.caption("Trained on stays discharged by 1 December 2019, judged on stays admitted from "
           "2020. The model flags as many stays as the rule does. It beats the rule only "
           "if the 95% interval of the difference, resampling patients, is above 0. Under "
           "30 readmissions is too few to judge.")
for population, label in POPULATIONS.items():
    row = results[(results["population"] == population) & (results["scorer"] == "model")
                  & (results["patients"] == "all")].iloc[0]
    st.markdown(f"**{label}** · champion: {row.model_kind} · **{row.model_verdict}**")
    st.caption(f"Readmissions caught, model minus rule: {100 * row.diff_mid:+.1f} points "
               f"(95% interval {100 * row.diff_low:+.1f} to {100 * row.diff_high:+.1f}).")

st.header("Readmissions caught, at the same number of alerts")
every = results[results["patients"] == "all"]
table = pd.DataFrame({
    "Population": every["population"].map(POPULATIONS),
    "Scored by": every["scorer"].map(SCORERS),
    "Caught %": every["recall"].map(lambda v: "hidden" if pd.isna(v) else f"{100 * v:.1f}"),
    "Average precision": every["avg_precision"].round(3),
    "Average precision, cross-validated": every["cv_avg_precision"].round(3),
    "Brier": every["brier"].round(4),
})
st.dataframe(table, hide_index=True, use_container_width=True)
breakdown = results[(results["patients"] != "all") & (results["scorer"] == "model")]
st.caption("Average precision and Brier are reported; they do not decide. The rule's "
           "are hidden with its recall: for a yes/no rule they give the counts back. "
           "Cross-validated is the champion's score on training folds it did not see. "
           "By patient (new: no stay in the training years): "
           + "; ".join(f"{POPULATIONS[r.population].lower()}, {PATIENTS[r.patients].lower()}: "
                       f"{r.model_verdict}" for r in breakdown.itertuples())
           + ". No numbers are shown for these: some hold 1-10 readmissions.")

st.header("Has the data moved since training?")
features = drift[drift["drift_check"] == "feature"].sort_values("value", ascending=False)
st.dataframe(pd.DataFrame({"Feature": features["subject"], "PSI": features["value"].round(3),
                           "Status": features["status"].map(STATUS)}),
             hide_index=True, use_container_width=True)
st.caption("PSI compares each feature's spread in 2020-2026 with training: under 0.1 "
           "stable, 0.1-0.25 watch, over 0.25 shifted. A true/false feature is judged by "
           "its rate instead: if training's rate falls outside the 95% interval of the "
           "2020-2026 rate, it is watch, and shifted when the two differ by 5 points or "
           "more. PSI barely moves on two values: heart disease went from about 22% to 35% "
           "of stays at a PSI of 0.09.")
flags = drift[drift["drift_check"] == "flag_rate"]
st.line_chart(flags.assign(pct=100 * flags["value"])
                   .pivot(index="period", columns="subject", values="pct"))
st.caption("Share of stays each champion flags per year. Its cutoff was fixed at training "
           "time, on training stays it had not seen, to flag as many as the rule did then "
           "(about 22%); a move away from that is drift, not an error.")
rate = drift[drift["drift_check"] == "readmission_rate"]
st.dataframe(pd.DataFrame({
    "Population": rate["subject"].map(POPULATIONS), "Period": rate["period"],
    "Readmission rate %": (100 * rate["value"]).round(2),
    "95% interval %": [f"{100 * lo:.2f}-{100 * hi:.2f}"
                       for lo, hi in zip(rate["low"], rate["high"], strict=True)],
    "Status": rate["status"].map(STATUS)}), hide_index=True, use_container_width=True)
st.caption("Stable means training's readmission rate lies inside this interval. "
           "Training's own rate is not shown: with the totals, it would narrow down a "
           "group of 1-10.")
