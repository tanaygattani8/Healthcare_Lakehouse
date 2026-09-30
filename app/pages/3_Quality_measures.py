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
st.title("Readmissions and care gaps")
st.caption("Built in the gold layer from 1,148 synthetic patients. Counts only.")

readmit_path, gap_path = SNAPSHOTS / "gold_readmission.parquet", SNAPSHOTS / "gold_care_gap.parquet"
if not readmit_path.exists() or not gap_path.exists():
    st.error("No gold snapshot. Run `python -m scripts.publish_snapshot`.")
    st.stop()

r = pd.read_parquet(readmit_path).iloc[0]
st.subheader("30-day readmissions")
left, middle, right = st.columns(3)
left.metric("Readmission rate", f"{100 * r.readmitted / r.index_stays:.2f}%")
middle.metric("Index stays", f"{int(r.index_stays):,}")
right.metric("Readmitted within 30 days", f"{int(r.readmitted):,}")
st.dataframe(pd.DataFrame({
    "": ["Hospital stays", "Encounters merged into a longer stay",
         "Excluded: died during the stay", "Excluded: under 30 days of data after discharge",
         "Excluded: discharged to hospice", "Index stays (can start a 30-day window)"],
    "count": [r.stays, r.encounters_merged, r.excl_died, r.excl_short_followup,
              r.excl_hospice, r.index_stays],
}).astype({"count": int}), hide_index=True, use_container_width=True)
st.caption(
    "A stay, not an encounter: an encounter that starts before the last one ended, or "
    "the same day, is the same stay. Counting each encounter gave 15.97%, because the "
    "middle of a stay counted as a patient who never came back. A return for a planned "
    "reason (sterilization, awaiting a kidney transplant, a sleep study) does not count."
)

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
