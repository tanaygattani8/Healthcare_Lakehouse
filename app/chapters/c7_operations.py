"""Chapter 7: the operations dashboard's default view (D74), names made up at publish."""

import altair as alt
import pandas as pd
import streamlit as st
import ui

k = ui.snapshot("ops_kpi").iloc[0]
visits = ui.snapshot("ops_visits")
quarters = ui.snapshot("ops_stays")
payers = ui.snapshot("ops_payers")
hospitals = ui.snapshot("ops_hospitals")
gaps = ui.snapshot("gold_care_gap").assign(rate=lambda d: d["met"] / d["eligible"])
p = ui.palette()

VISIT_TYPES = {"ambulatory": "Ambulatory", "wellness": "Wellness", "outpatient": "Outpatient",
               "urgentcare": "Urgent care", "emergency": "Emergency", "other": "Other",
               "inpatient": "Inpatient"}
MEASURES = {"bp_control": "blood pressure control",
            "diabetes_hba1c": "HbA1c testing for diabetics",
            "statin_therapy": "statins for heart patients"}
window = f"{k.window_start:%b %Y} – {k.last_month:%b %Y}"
prior = f"{k.prior_start:%b %Y} – {k.prior_end:%b %Y}"
# Year labels that drop out instead of colliding on a phone.
YEARS = alt.Axis(format="%Y", tickCount="year", labelOverlap="greedy", labelSeparation=6)


def money(v) -> str:
    return f"${v / 1000:.1f}K"


def first(text: str) -> str:
    return text[0].upper() + text[1:]


def shown(*values) -> bool:
    """A finding is written only when every number in it is shown."""
    return not any(pd.isna(v) for v in values)


ui.chapter(7, "The operations dashboard", "Running the network",
           "What a hospital quality and operations director opens on a Monday: the last twelve "
           "complete months against the twelve before, where the stays and the money go, and "
           "three things to do about it. Every number is the Databricks dashboard's own "
           "default view, run by its own SQL.", wide=True)

ui.heading("7 · 1", f"The last twelve months ({window})")
# The tiles take the full width, with their notes across underneath.
ui.numbers([
    (f"{k.visits / 1000:.1f}K", "visits",
     f"was {k.visits_prior / 1000:.1f}K · {k.visits_change_pct:+.1f}%"),
    (f"{k.stays:,.0f}", "hospital stays",
     f"was {k.stays_prior:,.0f} · {k.stays_change_pct:+.1f}%"),
    (f"{k.avg_length_of_stay_days:.1f} d", "average length of stay",
     f"was {k.avg_length_of_stay_days_prior:.1f} · {k.length_of_stay_change_days:+.1f} d"),
    (money(k.cost_per_stay), "cost per stay",
     f"was {money(k.cost_per_stay_prior)} · {k.cost_change_pct:+.1f}%"),
    (f"{k.readmission_rate_pct_2020_2026:.2f}%", "30-day readmissions, 2020–2026",
     f"was {k.readmission_rate_pct_2010_2019:.2f}% in 2010–2019"),
])
ui.notes(f"Each tile is {window} against {prior}. The window is computed from the last day of "
         "data, never typed. <i>D74</i>",
         "Readmissions use whole periods: at about 500 stays a year, twelve months would almost "
         "always hold 1–10 readmissions, and be hidden. <i>D70</i>",
         "The dashboard itself lives in Databricks behind the workspace login, with payer, "
         "hospital and visit-type filters. It ships as code: "
         "<code>dashboards/operations.lvdash.json</code>.", across=True)

ui.heading("7 · 2", "What they say, and what to do")
main, side = ui.section()
findings, actions = [], []
with main:
    if shown(k.stays_change_pct, k.cost_change_pct, k.length_of_stay_change_days):
        head = (f"{'More' if k.stays_change_pct > 0 else 'Fewer'} stays, "
                f"{'cheaper' if k.cost_change_pct < 0 else 'costlier'} and "
                f"{'shorter' if k.length_of_stay_change_days < 0 else 'no shorter'}.")
        findings.append(
            f"<b>{head}</b> Hospital stays {'rose' if k.stays_change_pct > 0 else 'fell'} "
            f"{abs(k.stays_change_pct):.1f}% ({k.stays:,.0f} against {k.stays_prior:,.0f}) "
            f"while cost per stay {'fell' if k.cost_change_pct < 0 else 'rose'} "
            f"{abs(k.cost_change_pct):.1f}% ({money(k.cost_per_stay)} against "
            f"{money(k.cost_per_stay_prior)}) and the average stay went from "
            f"{k.avg_length_of_stay_days_prior:.1f} to {k.avg_length_of_stay_days:.1f} days. "
            + (f"Visits held flat ({k.visits / 1000:.1f}K against {k.visits_prior / 1000:.1f}K)."
               if abs(k.visits_change_pct) < 2 else
               f"Visits moved {k.visits_change_pct:+.1f}%."))
    named = payers.dropna(subset=["stays"])
    top = named.iloc[0]
    if shown(top.stays, top.cost_per_stay):
        costliest = top.cost_per_stay == named["cost_per_stay"].max()
        findings.append(
            f"<b>{ui.esc(top.payer)} carries {top.stays / k.stays:.0%} of the stays"
            f"{', at the highest cost' if costliest else ''}.</b> {top.stays:,.0f} of "
            f"{k.stays:,.0f} stays at {money(top.cost_per_stay)} each, against "
            f"{money(k.cost_per_stay)} across the network.")
    long = named[named["avg_length_of_stay_days"] >= k.avg_length_of_stay_days + 0.5]
    if len(long):
        actions.append(
            f"<b>Review discharge planning for {' and '.join(map(ui.esc, long['payer']))} "
            f"stays.</b> They run "
            f"{' and '.join(f'{d:.1f}' for d in long['avg_length_of_stay_days'])} days against "
            f"the network's {k.avg_length_of_stay_days:.1f}.")
    worst = gaps.sort_values("rate").iloc[0]
    others = gaps[gaps["measure"] != worst.measure]
    findings.append(
        f"<b>{first(MEASURES[worst.measure])} is the widest care gap.</b> {worst.rate:.1%} of "
        f"{worst.eligible:,} eligible patients met it in {worst.measure_year}, against "
        + " and ".join(f"{r.rate:.1%} for {MEASURES[r.measure]}"
                       for r in others.itertuples()) + ".")
    biggest = worst.eligible == gaps["eligible"].max()
    actions.insert(0, f"<b>Start a {MEASURES[worst.measure]} outreach programme.</b> It "
                      f"is the widest gap{', on the largest group' if biggest else ''}. Measure "
                      "it by this closure rate in the next measure year.")
    recent = quarters.tail(8)
    thin = int((hospitals["stays"] <= 20).sum())
    actions.append(
        "<b>Check case mix before crediting the cost change.</b> Cost per stay swung between "
        f"{money(recent['cost_per_stay'].min())} and {money(recent['cost_per_stay'].max())} "
        f"over the last eight quarters, and {thin} of the {len(hospitals)} hospitals below "
        "rest on 11–20 stays. Read single hospitals over a longer window before acting.")
    for text in findings:
        ui.finding(text)
    st.html('<div class="lh-kicker" style="margin-top:1.4rem">What to do about it</div>')
    for text in actions:
        ui.finding(text)
with side:
    ui.notes("Written by this page from the snapshot, so a new publish rewrites it. A finding "
             "whose number is hidden is left out, not shown with a gap.",
             f"Synthetic data (Synthea): a {k.readmission_rate_pct_2020_2026:.2f}% readmission "
             "rate is far below real-world levels.",
             "Care gaps are chapter 3's measures, for the whole network.")

ui.heading("7 · 3", "Visits, month by month")
main, side = ui.section()
with main:
    order = visits.groupby("visit_type")["visits"].sum().sort_values(ascending=False).index
    v = visits.assign(type=visits["visit_type"].map(VISIT_TYPES))
    # Separate charts, not a facet: facets clip on phones. Only the last shows years.
    for i, t in enumerate(order):
        last = i == len(order) - 1
        chart = alt.Chart(v[v["visit_type"] == t]).mark_line(
            strokeWidth=1.6, color=p["series"][0]).encode(
            x=alt.X("visit_month:T", title=None,
                    axis=YEARS if last else None),
            y=alt.Y("visits:Q", title=None,  # a fixed gutter lines the rows up
                    axis=alt.Axis(tickCount=2, format="~s", minExtent=34, maxExtent=34)),
            tooltip=[alt.Tooltip("type:N", title="visit type"),
                     alt.Tooltip("visit_month:T", title="month", format="%b %Y"),
                     alt.Tooltip("visits:Q", format=",")],
        ).properties(height=48, autosize=alt.AutoSizeParams(type="fit-x", contains="padding"),
                     title=alt.TitleParams(
            VISIT_TYPES[t], anchor="start", fontSize=12, fontWeight=600, color=p["ink"]))
        if last:
            ui.figure(chart, "7.1", "Visits per month by type, largest first, "
                      f"{v['visit_month'].min():%b %Y} to {v['visit_month'].max():%b %Y}. Each "
                      "row has its own scale: compare shapes, not heights.")
        else:
            st.altair_chart(ui.themed(chart), width="stretch", theme=None)
with side:
    ui.notes("Inpatient visits double in the winter of 2020–21 and outpatient visits jump "
             "six-fold in spring 2021, when Synthea's COVID-19 module runs: the generator, not "
             "a change in how the network works.",
             "No month is hidden. A hidden one would come back by subtraction from the "
             "twelve-month tile, so the publish refuses it.")

ui.heading("7 · 4", "Length of stay and cost, quarter by quarter")
q = quarters.assign(quarter=quarters["admit_quarter"].dt.to_period("Q").astype(str))
left, right = st.columns(2, gap="large")
for col, field, title, fmt, now, number, cap in (
        (left, "avg_length_of_stay_days", "days", ".1f", k.avg_length_of_stay_days, "7.2",
         "Average length of stay by quarter of admission."),
        (right, "cost_per_stay", "cost per stay", "$,.0f", k.cost_per_stay, "7.3",
         "Cost per stay by quarter of admission.")):
    base = alt.Chart(q).encode(
        x=alt.X("admit_quarter:T", title=None, axis=YEARS),
        tooltip=[alt.Tooltip("quarter:N"), alt.Tooltip(f"{field}:Q", title=title, format=fmt),
                 alt.Tooltip("stays:Q", format=",")])
    y = alt.Y(f"{field}:Q", title=title, scale=alt.Scale(zero=False),
              axis=alt.Axis(format="$~s", tickCount=4) if field == "cost_per_stay"
              else alt.Axis(format=".0f", tickMinStep=1))
    line = base.mark_line(strokeWidth=1.6, color=p["series"][0]).encode(y=y)
    dots = base.mark_point(filled=True, size=22, color=p["series"][0]).encode(y=y)
    rule = alt.Chart(pd.DataFrame({"v": [now]})).mark_rule(
        color=p["accent"], strokeDash=[5, 4], strokeWidth=1.4).encode(y="v:Q")
    with col:
        ui.figure((rule + line + dots).properties(height=230), number,
                  f"{cap} Dashed: the last twelve months. About {q['stays'].median():.0f} "
                  "stays a quarter, so a few unusual stays move it.")

ui.heading("7 · 5", "By payer, by hospital")
main, side = ui.section()
with main:
    ui.table(payers.rename(columns={"avg_length_of_stay_days": "avg stay (days)",
                                    "cost_per_stay": "cost per stay ($)"}),
             {"avg stay (days)": ".1f", "cost per stay ($)": ",.0f"}, missing="hidden")
    ui.table(hospitals.rename(columns={
                 "avg_length_of_stay_days": "avg stay (days)",
                 "length_of_stay_vs_network_days": "vs network (days)",
                 "cost_per_stay": "cost per stay ($)", "cost_vs_network_pct": "vs network (%)"}),
             {"avg stay (days)": ".1f", "vs network (days)": "+.1f",
              "cost per stay ($)": ",.0f", "vs network (%)": "+.1f"}, missing="hidden")
with side:
    hidden = int(payers["stays"].isna().sum())
    ui.notes(f"Last twelve months. {hidden} of {len(payers)} payers are hidden: any with 1–10 "
             "stays, and the fewest larger ones that stop the stays tile minus the shown rows "
             "from giving a small one back. <i>E61</i>",
             "Hospitals with 1–10 stays are left out. Some \"hospitals\" are outpatient "
             "clinics that hold inpatient encounters.",
             "Names are made up. Synthea takes its hospitals and insurers from real ones, and "
             "these costs are synthetic, so only government programmes keep their names.")

ui.pager(7)
