from pathlib import Path

import pandas as pd
import streamlit as st

SNAPSHOTS = Path(__file__).parent.parent.parent / "snapshots"
# Short, because the chart cuts long labels: BP under 140/90, diabetics with
# an HbA1c test, heart patients on a statin.
MEASURES = {"bp_control": "Blood pressure",
            "diabetes_hba1c": "HbA1c test",
            "statin_therapy": "Statin"}

st.set_page_config(page_title="Quality measures", page_icon="🏥")
st.title("Care gaps")
st.page_link("pages/4_Readmission_story.py",
             label="Readmissions have their own page: the readmission story")
st.caption("Built in the gold layer from 12,580 synthetic patients. Counts only.")

gap_path = SNAPSHOTS / "gold_care_gap.parquet"
if not gap_path.exists():
    st.error("No gold snapshot. Run `python -m scripts.publish_snapshot`.")
    st.stop()

gaps = pd.read_parquet(gap_path)
gaps["measure"] = gaps["measure"].map(MEASURES)
gaps["met %"] = (100 * gaps["met"] / gaps["eligible"]).round(1)
year = int(gaps["measure_year"].iloc[0])
st.subheader(f"Care gaps, {year}")
st.bar_chart(gaps.set_index("measure")["met %"], horizontal=True)
st.dataframe(
    gaps[["measure", "in_denominator", "excl_age", "excl_died", "excl_hospice",
          "eligible", "met", "gaps", "met %"]].sort_values("measure"),
    hide_index=True, use_container_width=True,
)
st.caption(
    "Read these as the generator's rules, not as a finding about care. Synthea "
    "prescribes a statin as part of the heart treatment it simulates, so the statin "
    "rate says how the data was made. The other two land where real-world rates do, "
    "which is also what the generator was tuned to. Only people alive on 1 January "
    "are in a measure's group."
)

st.divider()
st.caption("Synthetic data from Synthea. Counts only: no patient-level rows.")
