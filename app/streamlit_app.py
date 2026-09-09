from pathlib import Path

import pandas as pd
import streamlit as st

SNAPSHOT = Path(__file__).parent.parent / "snapshots" / "bronze_counts.parquet"

st.set_page_config(page_title="Healthcare Lakehouse", page_icon="🏥")

st.title("Healthcare Lakehouse")
st.caption("Synthetic EHR data on a Databricks medallion architecture. Bronze and silver.")

if not SNAPSHOT.exists():
    st.error("No snapshot found. Run `python -m scripts.publish_snapshot`.")
    st.stop()

df = pd.read_parquet(SNAPSHOT)
captured = pd.to_datetime(df["captured_at"].iloc[0])

# Snapshots written before phase 2 have no layer column; treat them as bronze.
if "layer" not in df.columns:
    df["layer"] = "bronze"

bronze = df[df["layer"] == "bronze"]
silver = df[df["layer"] == "silver"]
quarantine = df[df["layer"] == "quarantine"]

quarantined = int(quarantine["rows"].sum())
modelled = int(silver["rows"].sum()) + quarantined
rate = (quarantined / modelled * 100) if modelled else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Bronze rows", f"{bronze['rows'].sum():,}")
col2.metric("Silver rows", f"{silver['rows'].sum():,}")
col3.metric("Quarantined", f"{quarantined:,}", f"{rate:.4f}% of input")

st.caption(f"Snapshot captured {captured:%Y-%m-%d %H:%M} UTC")

if not silver.empty:
    st.subheader("Silver — the clinical model")
    st.bar_chart(silver.set_index("entity")["rows"])

    st.subheader("Data quality")
    dq = silver[["entity", "rows"]].merge(
        quarantine[["entity", "rows"]],
        on="entity",
        how="left",
        suffixes=("_passed", "_quarantined"),
    )
    dq["rows_quarantined"] = dq["rows_quarantined"].fillna(0).astype(int)
    dq["failure_rate_pct"] = (
        dq["rows_quarantined"] / (dq["rows_passed"] + dq["rows_quarantined"]) * 100
    ).round(4)
    st.dataframe(dq, use_container_width=True, hide_index=True)
    st.caption(
        "Rows failing a quality rule move to a quarantine table rather than "
        "being deleted, so a failure is visible instead of silent."
    )

st.subheader("Bronze — raw ingest")
st.bar_chart(bronze.set_index("entity")["rows"])

st.divider()
st.caption(
    "Data is synthetic, generated with Synthea. It contains no real patient "
    "information. Aggregate counts only — no record-level data leaves the "
    "lakehouse."
)
