from pathlib import Path

import pandas as pd
import streamlit as st

SNAP = Path(__file__).parent.parent.parent / "snapshots"
NAMES = {
    "admit_year": "Year admitted", "age_band": "Age band", "gender": "Gender",
    "has_diabetes": "Diabetes", "has_hypertension": "Hypertension",
    "has_cardiovascular_disease": "Heart disease or stroke",
    "above_median_conditions": "More conditions than the median",
    "admit_reason_group": "Admit reason", "is_planned": "Planned admission",
    "above_median_length_of_stay": "Longer stay than the median",
    "prior_stays_12m_band": "Hospital stays in the year before",
    "prior_emergency_12m_band": "Emergency visits in the year before",
    "post_followup_7d": "Follow-up visit within 7 days (after discharge)",
}
CONTESTANTS = {"answer_key": "control: the answer key", "raw": "Llama 3.3 70B + gold tables",
               "metrics": "Llama 3.3 70B + metric views", "genie": "Genie + metric views"}
TIERS = {1: "1 · one table", 2: "2 · filters, groups", 3: "3 · a measure with its rules",
         4: "4 · should refuse"}
# Filled in Task 12 from decision.md: signal -> "generator rule: <module>" or
# "not traced". A signal missing here is "not checked" (spec §4).
LABELS: dict[str, str] = {}
# Filled in Task 12: chapter number -> its one-line finding, from the numbers.
FINDINGS: dict[int, str] = {}

st.set_page_config(page_title="The readmission story", page_icon="🏥")
st.title("Who comes back, and could we see it coming?")
st.caption("Synthetic data from Synthea, so no finding here is about real patients. "
           "Counts only; any group with 1-10 stays or readmissions is hidden.")

paths = {name: SNAP / f"story_{name}.parquet" for name in ("totals", "levels", "verdict")}
if not all(path.exists() for path in paths.values()):
    st.error("No story snapshot. Run `python -m scripts.publish_snapshot`.")
    st.stop()
t = pd.read_parquet(paths["totals"]).iloc[0]
levels = pd.read_parquet(paths["levels"])
decision = pd.read_parquet(paths["verdict"]).iloc[0]
shown = levels[~levels["suppressed"]].assign(**{"rate %": lambda d: (100 * d["rate"]).round(1)})


def finding(chapter: int) -> None:
    if chapter in FINDINGS:
        st.info(FINDINGS[chapter])


def rates(signal: str) -> None:
    rows = shown[shown["signal"] == signal]
    label = LABELS.get(signal, "not checked")
    st.markdown(f"**{NAMES[signal]}** · {label}")
    if not rows.empty:
        st.bar_chart(rows.set_index("level")["rate %"], horizontal=True, height=160)
    hidden = levels[(levels["signal"] == signal) & levels["suppressed"]]["level"]
    if not hidden.empty:
        st.caption(f"Hidden: {', '.join(hidden)} (1-10 stays or readmissions, or the one "
                   "level that would give a hidden count back by subtraction).")


st.header("1 · How big is the problem?")
left, middle, right = st.columns(3)
left.metric("30-day readmission rate", f"{100 * t.readmitted / t.index_stays:.2f}%")
middle.metric("Readmitted / index stays", f"{int(t.readmitted):,} / {int(t.index_stays):,}")
right.metric("Patients behind the readmissions", f"{int(t.readmitted_patients):,}")
st.dataframe(pd.DataFrame({
    "": ["Hospital stays", "Encounters merged into a longer stay",
         "Excluded: died during the stay", "Excluded: under 30 days of data after discharge",
         "Excluded: discharged to hospice", "Excluded: cancer treatment (planned, D64)",
         "Index stays (can start a 30-day window)"],
    "count": [t.stays, t.encounters_merged, t.excl_died, t.excl_short_followup,
              t.excl_hospice, t.excl_cancer_treatment, t.index_stays],
}).astype({"count": int}), hide_index=True, use_container_width=True)
years = shown[shown["signal"] == "admit_year"].sort_values("level")
st.bar_chart(years.set_index("level")[["index_stays", "readmitted"]], height=220)
st.caption("By year admitted. Each year has only a few dozen index stays, so a single "
           "year's rate is noise; the counts are shown, not the rate.")
finding(1)

st.header("2 · Who comes back?")
for signal in ("age_band", "gender", "has_diabetes", "has_hypertension",
               "has_cardiovascular_disease", "above_median_conditions"):
    rates(signal)
finding(2)

st.header("3 · What happened around the stay?")
for signal in ("admit_reason_group", "is_planned", "above_median_length_of_stay",
               "prior_stays_12m_band", "prior_emergency_12m_band", "post_followup_7d"):
    rates(signal)
st.caption("Follow-up happens after discharge: it can explain readmissions, but a model "
           "scoring patients at discharge cannot use it.")
finding(3)

st.header("4 · What does it cost?")
left, right = st.columns(2)
left.metric("Index stays", f"${t.index_stay_cost:,.0f}",
            f"${t.index_stay_cost / t.index_stays:,.0f} per stay", delta_color="off")
right.metric("The stays that came back", f"${t.return_stay_cost:,.0f}",
             f"${t.return_stay_cost / t.readmitted:,.0f} per return stay", delta_color="off")
finding(4)

st.header("5 · Could we see it coming?")
st.caption("Each signal known at discharge, one level against the rest. A level separates "
           "when both sides have 30+ stays, the higher rate comes from 10+ different "
           "patients, and the 95% ranges do not overlap. The rule was fixed before the "
           "numbers were looked at.")
# Hidden levels stay in the table, without numbers: their decision was made
# on the real counts and is part of the verdict (D66).
table = levels[levels["at_discharge"] & (levels["signal"] != "admit_year")].assign(
    signal=lambda d: d["signal"].map(NAMES),
    **{"rate % (95% range)": lambda d: d.apply(
        lambda r: "hidden" if r.suppressed else
        f"{100 * r.rate:.1f} ({100 * r.low:.1f}-{100 * r.high:.1f})", axis=1),
       "rest % (95% range)": lambda d: d.apply(
        lambda r: "hidden" if r.suppressed else
        f"{100 * r.rest_rate:.1f} ({100 * r.rest_low:.1f}-{100 * r.rest_high:.1f})",
        axis=1)})
st.dataframe(table[["signal", "level", "index_stays", "rate % (95% range)",
                    "rest % (95% range)", "separates"]],
             hide_index=True, use_container_width=True)
short = sorted(levels[levels["separates"] & levels["at_discharge"]]["signal"].unique())
st.subheader(f"Phase 6: {decision.decision}")
st.write(f"{len(short)} signal(s) separate: "
         + (", ".join(f"{NAMES[s]} ({LABELS.get(s, 'not checked')})" for s in short) or "none")
         + ". GO needs at least 2.")
finding(5)

st.header("Can you ask this in English?")
scores_path = SNAP / "eval_scores.parquet"
if scores_path.exists():
    scores = pd.read_parquet(scores_path)
    name = "test" if (scores["set_name"] == "test").any() else "dev"
    s = scores[(scores["set_name"] == name) & (scores["run_no"] == 1)]
    s = (s.assign(correct=s["answers"].where(s["verdict"] == "correct", 0))
          .groupby(["contestant", "tier"], as_index=False)[["correct", "answers"]].sum())
    st.dataframe(s.assign(contestant=s["contestant"].map(CONTESTANTS), tier=s["tier"].map(TIERS),
                          score=s["correct"].astype(str) + " of " + s["answers"].astype(str))
                  .pivot(index="contestant", columns="tier", values="score"),
                 use_container_width=True)
    st.caption(f"The story's own questions ({name} set), asked in English. Each answer's SQL "
               "was run and compared with a hand-checked answer. Counts, not percentages: "
               "each tier has only a few questions.")
