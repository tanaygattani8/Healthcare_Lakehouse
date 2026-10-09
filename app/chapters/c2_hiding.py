"""Chapter 2: de-identification scored against the answer key; who is still findable."""

import altair as alt
import streamlit as st
import ui

NAMES = {"roster": "0 · the answer sheet", "regex": "1 · patterns",
         "ner": "2 · name model", "llm": "3 · language model"}
KANON = {"plan": "birth date + ZIP3 + gender",
         "safe": "Safe Harbor: birth year + ZIP3 + gender",
         "released": "released: 5-year bands, no ZIP"}
ORDER = ["1", "2", "3", "4", "5-10", "11+"]

scores = ui.snapshot("deid_scores")
scores["program"] = scores["stage"].map(NAMES)
real = scores[scores["real_items"].notna()]
kanon = ui.snapshot("deid_kanon")
kanon["version"] = kanon["version"].map(KANON)
p = ui.palette()
alone = int(kanon.query("version == @KANON['safe'] and k == '1'")["people"].sum())
people = int(kanon.query("version == @KANON['safe']")["people"].sum())
released = kanon.query("version == @KANON['released'] and people > 0")["k"]
floor = next(k for k in ORDER if k in set(released))  # the smallest group anyone is in

ui.chapter(2, "De-identification", "Hiding the patients",
           "Clinical notes name people. Four programs searched 25 test patients' notes for "
           "private details and were marked against an answer sheet built from each patient's "
           "own record. Then a harder question: with the details removed, could anyone still "
           "be picked out?")

main, side = ui.section()
with main:
    best = real[real["stage"] != "roster"].groupby("phi_category")["covered_recall"].max()
    ui.numbers([(f"{100 * best.get('name', 0):.0f}%", "of names hidden by the best program"),
                (f"{alone:,} of {people:,}", "people still unique under Safe Harbor alone"),
                (f"k ≥ {floor.split('-')[0].rstrip('+')}",
                 "in the released table: the smallest group anyone is in")])
    recall = alt.Chart(real).mark_bar(height=12, color=p["series"][0]).encode(
        x=alt.X("covered_recall:Q", title="share of real items hidden", axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("program:N", title=None, sort=list(NAMES.values())),
        tooltip=["program:N", "phi_category:N",
                 alt.Tooltip("covered_recall:Q", title="hidden", format=".0%"),
                 alt.Tooltip("real_items:Q", title="real items")])
    ui.figure(recall.properties(height=110, width=170)
              .facet(column=alt.Column("phi_category:N", title=None), spacing=18), "2.1",
              "Recall by kind of detail. An item counts only if one guess covered all of it: "
              "finding 'Luc' in 'Lucius' leaves 'ius' in the note.")
with side:
    ui.notes("Recall matters more than precision here. A miss is someone's name left in a "
             "note; a false alarm is a word blanked that did not need to be.",
             "Program 0 is the answer sheet itself; its perfect score proves the marking works.",
             "Program 1's perfect dates are a property of synthetic notes, where every "
             "date-shaped string is a real date. It finds no names.")

ui.heading("Re-identification", "Could anyone still be picked out?")
main, side = ui.section()
with main:
    k = (kanon.set_index(["version", "k"])["people"].unstack().reindex(columns=ORDER)
         .fillna(0).stack().rename("people").reset_index())
    bars = alt.Chart(k).mark_bar(color=p["series"][1]).encode(
        x=alt.X("k:N", sort=ORDER, title="people sharing their details (k)",
                axis=alt.Axis(labelAngle=0)),
        y=alt.Y("people:Q", title="people"),
        tooltip=["version:N", "k:N", alt.Tooltip("people:Q", format=",")])
    ui.figure(bars.properties(height=150, width=165)
              .facet(column=alt.Column("version:N", title=None, sort=list(KANON.values())),
                     spacing=16), "2.2",
              "People grouped by how many others share their birth, death and gender details. "
              "k = 1 means alone and findable.")
with side:
    ui.notes(f"Following Safe Harbor's rules still left {alone:,} of {people:,} people unique: "
             "the rule is a checklist, not a guarantee.",
             "The released table has nobody below 5. De-identification covers the first "
             "Synthea batch, the one with notes.")

with ui.method("Every program's scores, and its false alarms"):
    ui.table(real[["program", "phi_category", "real_items", "guesses", "precision", "recall",
                   "covered_recall", "exact_recall"]].sort_values(["phi_category", "program"]))
    false = scores[scores["real_items"].isna()]
    ui.table(false[["program", "phi_category", "guesses"]])
    st.caption("False alarms: flagged as private where the test notes hold none. Ages under 90, "
               "insurers read as identifiers, ethnicity read as a place, doses read as ZIP codes.")

ui.pager(2)
