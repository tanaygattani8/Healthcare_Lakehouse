from pathlib import Path

import pandas as pd
import streamlit as st

SNAPSHOTS = Path(__file__).parent.parent.parent / "snapshots"
NAMES = {"roster": "0 · look up the patient", "regex": "1 · patterns",
         "ner": "2 · name model", "llm": "3 · language model"}

st.set_page_config(page_title="De-identification", page_icon="🏥")
st.title("How well are patient details hidden?")
st.caption(
    "Four programs searched 25 test patients' clinical notes for private details, "
    "and were marked against an answer sheet built from each patient's own record."
)

scores_path, kanon_path = SNAPSHOTS / "deid_scores.parquet", SNAPSHOTS / "deid_kanon.parquet"
if not scores_path.exists() or not kanon_path.exists():
    st.error("No de-identification snapshot. Run `python -m scripts.publish_snapshot`.")
    st.stop()

scores = pd.read_parquet(scores_path)
scores["program"] = scores["stage"].map(NAMES)
real = scores[scores["real_items"].notna()]

st.subheader("Recall: how much was hidden")
st.caption(
    "A real item counts only if one guess covered all of it; finding 'Luc' in "
    "'Lucius' leaves 'ius' in the document. Recall matters more than precision "
    "here. A miss is someone's name left in a note; a false alarm is a word "
    "blanked that did not need to be."
)
st.bar_chart(real.pivot(index="program", columns="phi_category", values="covered_recall"),
             stack=False)
st.dataframe(
    real[["program", "phi_category", "real_items", "guesses", "precision",
          "recall", "covered_recall", "exact_recall"]].sort_values(["phi_category", "program"]),
    hide_index=True, use_container_width=True,
)
st.caption(
    "Program 0 is the answer sheet itself; its perfect score proves the marking works. "
    "Program 1's perfect dates are a property of synthetic notes, where every "
    "date-shaped string is a real date. It finds no names."
)

st.subheader("False alarms")
false = scores[scores["real_items"].isna()]
st.bar_chart(false.pivot(index="program", columns="phi_category", values="guesses"))
st.caption(
    "Flagged as private where the test notes hold none: ages under 90, insurers "
    "read as identifiers, ethnicity read as a place, drug doses read as ZIP codes."
)

st.subheader("Could anyone still be picked out?")
kanon = pd.read_parquet(kanon_path)
order = ["1", "2", "3", "4", "5-10", "11+"]
labels = {"plan": "birth date + ZIP3 + gender",
          "safe": "Safe Harbor: birth year + ZIP3 + gender",
          "released": "released: 5-year bands, no ZIP, k ≥ 5"}
table = (kanon.assign(version=kanon["version"].map(labels))
              .pivot(index="k", columns="version", values="people")
              .reindex(order).fillna(0).astype(int))
st.bar_chart(table, stack=False)
st.caption(
    "People grouped by how many others share their birth, death and gender details. "
    "k = 1 means alone and findable. Following Safe Harbor alone still left "
    f"{int(table.loc['1', labels['safe']]):,} of 1,148 people unique; the released "
    "table has nobody below 5."
)

st.divider()
st.caption("Synthetic data from Synthea. Counts only: no note text, names or records.")
