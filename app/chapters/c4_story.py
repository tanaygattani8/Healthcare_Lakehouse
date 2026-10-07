"""Chapter 4: the readmission story, in five sections, from the story
snapshots (phase 5). Any group with 1-10 stays or readmissions is hidden."""

import altair as alt
import pandas as pd
import streamlit as st
import ui

NAMES = {
    "admit_period": "Period admitted", "age_band": "Age band", "gender": "Gender",
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
FINDINGS = {
    1: "In this synthetic data, 140 of 10,724 index stays (1.31%) come back within 30 days, "
       "from 127 different patients. Chemotherapy (D64) and scheduled heart surgery (D68) "
       "are planned and do not count; before either rule, the rate was 12.31%.",
    2: "Stays with heart disease or stroke on the admit day come back 4.06% of the time, "
       "against 0.39% without. Ages 65-79 (3.18%), hypertension (2.48%), diabetes (2.11%) "
       "and men (1.66% against 1.02%) follow, mostly because they mark who has bypass "
       "surgery: Synthea sends 10.6% of bypass patients back to the ward.",
    3: "A stay begun for a bypass history comes back 9.74% of the time, the generator's 10.6%. "
       "Planned stays come back more often than unplanned (2.52% against 0.79%), because "
       "bypass surgery is planned and is where those returns start. A longer stay changes "
       "nothing. A follow-up visit within 7 days goes with more readmissions (2.95% against "
       "1.11%), not fewer; it happens after discharge, and probably marks the sicker patients.",
    5: "9 signals known at discharge separate, so phase 6 is GO by the rule fixed in advance. "
       "Take out the 91 returns from the bypass rule and 6 still separate: age, hypertension, "
       "more conditions, admit reason, planned admission and prior stays. Gender, diabetes and "
       "heart disease do not.",
}

t = ui.snapshot("story_totals").iloc[0]
levels = ui.snapshot("story_levels")
decision = ui.snapshot("story_verdict").iloc[0]
p = ui.palette()
overall = t.readmitted / t.index_stays
fig = iter(range(1, 50))


def rates(signals: list[str], caption: str) -> None:
    """Small multiples: one row per signal, each level's rate with its 95%
    interval, on one shared axis, against the overall rate (dashed). Hidden
    levels are named in the caption, never drawn."""
    rows = levels[levels["signal"].isin(signals) & ~levels["suppressed"]].assign(
        name=lambda d: d["signal"].map(NAMES), overall=overall)
    hidden = levels[levels["signal"].isin(signals) & levels["suppressed"]]
    top = float(rows["high"].max()) * 1.05
    scale = alt.Scale(domain=[0, top])
    shown = [s for s in signals if (rows["signal"] == s).any()]
    gone = "; ".join(f"{NAMES[s]}: {', '.join(g['level'])}"
                     for s, g in hidden.groupby("signal", sort=False))
    # One chart per signal rather than a facet: a facet has a fixed width and
    # clips on a phone; separate charts stretch. The x domain is fixed, so the
    # rows still share one axis, drawn under the last.
    for s in shown:
        last = s == shown[-1]
        axis = alt.Axis(format=".0%", tickMinStep=0.01) if last else None
        base = alt.Chart().encode(
            # One fixed label gutter, so the rows' x axes line up.
            y=alt.Y("level:N", title=None, sort=None,
                    axis=alt.Axis(minExtent=78, maxExtent=78, labelLimit=74)),
            tooltip=[alt.Tooltip("name:N", title="signal"), alt.Tooltip("level:N"),
                     alt.Tooltip("rate:Q", format=".2%"),
                     alt.Tooltip("low:Q", title="95% from", format=".2%"),
                     alt.Tooltip("high:Q", title="95% to", format=".2%"),
                     alt.Tooltip("index_stays:Q", title="index stays", format=",")])
        line = alt.Chart().mark_rule(color=p["accent"], strokeDash=[4, 4]).encode(
            x=alt.X("overall:Q", axis=axis, scale=scale))
        whisker = base.mark_rule(strokeWidth=2, color=p["muted"], opacity=0.75).encode(
            x=alt.X("low:Q", title="30-day readmission rate" if last else None, axis=axis,
                    scale=scale), x2="high:Q")
        dot = base.mark_point(filled=True, size=70, color=p["series"][0]).encode(
            x=alt.X("rate:Q", axis=axis, scale=scale))
        chart = alt.layer(line, whisker, dot, data=rows[rows["signal"] == s]).properties(
            height=alt.Step(22), autosize=alt.AutoSizeParams(type="fit-x", contains="padding"),
            title=alt.TitleParams(NAMES[s], anchor="start", fontSize=12, fontWeight=600,
                                  color=p["ink"]))
        if last:
            ui.figure(chart, f"4.{next(fig)}",
                      caption + (f" Hidden: {ui.esc(gone)}." if gone else ""))
        else:
            st.altair_chart(ui.themed(chart), width="stretch", theme=None)


ui.chapter(4, "The readmission story", "Who comes back, and could we see it coming?",
           "A 30-day readmission is a stay that starts within 30 days of an earlier discharge. "
           "This chapter counts them carefully, asks who they happen to and what happened "
           "around the stay, prices them, and ends on the question the next chapter answers: "
           "is any of it visible at discharge?")

ui.heading("4 · 1", "How big is the problem?")
main, side = ui.section()
with main:
    ui.numbers([(f"{100 * overall:.2f}%", "30-day readmission rate"),
                (f"{int(t.readmitted):,} / {int(t.index_stays):,}", "readmitted / index stays"),
                (f"{int(t.readmitted_patients):,}", "patients behind the readmissions")])
    ledger = pd.DataFrame({
        "": ["Hospital stays", "Encounters merged into a longer stay",
             "Excluded: died during the stay", "Excluded: under 30 days of data after discharge",
             "Excluded: discharged to hospice", "Excluded: cancer treatment (planned, D64)",
             "Index stays (can start a 30-day window)"],
        "count": [t.stays, t.encounters_merged, t.excl_died, t.excl_short_followup,
                  t.excl_hospice, t.excl_cancer_treatment, t.index_stays]}).astype({"count": int})
    ui.table(ledger)
    rates(["admit_period"], "Readmission rate by the period admitted.")
    ui.finding(FINDINGS[1])
with side:
    ui.notes("The dashed line on every figure is the overall rate; a dot's bar is its 95% "
             "interval.",
             "No single year has more than 10 readmissions, and this app hides 1-10, so the "
             "years are grouped until every period clears 10. <i>D70</i>",
             "Synthetic data from Synthea: no finding here is about real patients.")

ui.heading("4 · 2", "Who comes back?")
main, side = ui.section()
with main:
    rates(["has_cardiovascular_disease", "age_band", "has_hypertension", "has_diabetes",
           "gender", "above_median_conditions"],
          "Who the stays belong to, each level against the overall rate (dashed).")
    ui.finding(FINDINGS[2])
with side:
    ui.notes("Most of these trace to one rule in the generator, heart/cabg/postop: bypass "
             "patients are sent back to the ward 10.6% of the time. <i>D69</i>",
             "Heart disease or stroke, diabetes and gender are that rule. Age, hypertension "
             "and more conditions mostly are, but still separate without it.",
             "A hidden level had 1-10 stays or readmissions, or was the one level that would "
             "give a hidden count back by subtraction. <i>D66</i>")

ui.heading("4 · 3", "What happened around the stay?")
main, side = ui.section()
with main:
    rates(["admit_reason_group", "is_planned", "above_median_length_of_stay",
           "prior_stays_12m_band", "prior_emergency_12m_band", "post_followup_7d"],
          "What happened around the stay, each level against the overall rate (dashed).")
    ui.finding(FINDINGS[3])
with side:
    ui.notes("The bypass-history admit reason and planned admissions are the same rule; a "
             "CABG surgery stay is planned. <i>D68</i>",
             "Follow-up happens after discharge: it can explain readmissions, but a model "
             "scoring patients at discharge cannot use it.")

ui.heading("4 · 4", "What does it cost?")
main, side = ui.section()
with main:
    ui.numbers([(f"${t.index_stay_cost / 1e6:,.1f}M", f"index stays, "
                 f"${t.index_stay_cost / t.index_stays:,.0f} each"),
                (f"${t.return_stay_cost / 1e6:,.2f}M", f"the stays that came back, "
                 f"${t.return_stay_cost / t.readmitted:,.0f} each")])
    ui.finding("The expensive returns were scheduled heart surgery, which D68 counts as planned, "
               "so they are not in this bill.")
with side:
    ui.notes("Cost is the claim cost of every encounter inside the stay.")

ui.heading("4 · 5", "Could we see it coming?")
main, side = ui.section()
with main:
    short = sorted(levels[levels["separates"] & levels["at_discharge"]]["signal"].unique())
    ui.stamp(f"Phase 6 · {decision.decision}")
    table = levels[levels["at_discharge"]].assign(
        signal=lambda d: d["signal"].map(NAMES),
        index_stays=lambda d: d.apply(
            lambda r: "hidden" if r.suppressed else f"{int(r.index_stays):,}", axis=1),
        **{"rate % (95%)": lambda d: d.apply(
            lambda r: "hidden" if r.suppressed else
            f"{100 * r.rate:.1f} ({100 * r.low:.1f}–{100 * r.high:.1f})", axis=1),
           "rest % (95%)": lambda d: d.apply(
            lambda r: "hidden" if r.suppressed else
            f"{100 * r.rest_rate:.1f} ({100 * r.rest_low:.1f}–{100 * r.rest_high:.1f})",
            axis=1)})
    ui.table(table[["signal", "level", "index_stays", "rate % (95%)", "rest % (95%)",
                    "separates"]])
    ui.finding(FINDINGS[5])
with side:
    ui.notes("A level separates when both sides have 30+ stays, the higher rate comes from 10+ "
             "different patients, and the two 95% ranges do not overlap. The rule was fixed "
             "before the numbers were looked at.",
             f"{len(short)} signals separate; GO needed 2.",
             "Hidden levels stay in the table without numbers: their decision was made on the "
             "real counts and is part of the verdict. <i>D66</i>")

scores = ui.snapshot("eval_scores")
ui.heading("Appendix", "Can you ask this in English?")
main, side = ui.section()
with main:
    name = "test" if (scores["set_name"] == "test").any() else "dev"
    s = scores[scores["set_name"] == name]
    s = (s.assign(correct=s["answers"].where(s["verdict"] == "correct", 0))
          .groupby(["contestant", "run_no", "tier"], as_index=False)[["correct", "answers"]].sum())
    ui.table(s.assign(contestant=s["contestant"].map(CONTESTANTS), tier=s["tier"].map(TIERS),
                      score=s["correct"].astype(str) + " of " + s["answers"].astype(str))
              .pivot(index=["contestant", "run_no"], columns="tier", values="score")
              .reset_index().rename(columns={"run_no": "run"}))
with side:
    ui.notes(f"The story's own questions ({name} set), asked in English. Each answer's SQL was "
             "run and compared with a hand-checked answer.",
             "Counts, not percentages: each tier has only a few questions. Two identical runs "
             "move by 1-2 verdicts, so a gap that small is noise.")

ui.pager(4)
