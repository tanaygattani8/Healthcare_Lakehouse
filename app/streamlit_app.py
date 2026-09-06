from pathlib import Path

import pandas as pd 
import streamlit as st

SNAPSHOT = Path(__file__).parent.parent / "snapshots" / "bronze_counts.parquet"

st.set_page_config(page_title="Healthcare Lakehouse", page_icon="🏥")

st.title("Healthcare Lakehouse")
st.caption("Synthetic EHR data on a Databricks medallion architecture. Phase 1: bronze.")

if not SNAPSHOT.exists():
    st.error("No snapshot found. Run `python -m scripts.publish_snapshot`.")
    st.stop()

df = pd.read_parquet(SNAPSHOT)
captured = pd.to_datetime(df["captured_at"].iloc[0])

col1, col2 = st.columns(2)
col1.metric("Entities landed", len(df))
col2.metric("Total bronze rows", f"{df['rows'].sum():,}")

st.caption(f"Snapshot captured {captured:%Y-%m-%d %H:%M} UTC")

st.subheader("Rows per entity")
st.bar_chart(df.set_index("entity")["rows"])

st.subheader("Detail")
st.dataframe(df[["entity", "rows"]], use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Data is synthetic, generated with Synthea. It contains no real patient "
    "information. Aggregate counts only — no record-level data leaves the "
    "lakehouse."
)