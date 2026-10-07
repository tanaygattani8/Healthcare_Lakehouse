"""Chapter 1: bronze and silver. Every raw row lands; every row that fails a
rule is kept in quarantine rather than dropped."""

import altair as alt
import ui

df = ui.snapshot("bronze_counts")
if "layer" not in df.columns:  # snapshots from before phase 2
    df["layer"] = "bronze"
captured = df["captured_at"].iloc[0]
bronze = df[df["layer"] == "bronze"]
silver = df[df["layer"] == "silver"]
quarantine = df[df["layer"] == "quarantine"]
quarantined = int(quarantine["rows"].sum())
modelled = int(silver["rows"].sum()) + quarantined

ui.chapter(1, "Bronze and silver", "The data arrives",
           f"Synthea's records land untouched in bronze, {bronze['rows'].sum():,} rows across "
           f"{len(bronze)} files. Silver types and checks them: a row that breaks a rule is "
           "moved to a quarantine table, never deleted, so a failure is something you can "
           "count instead of something that silently went missing.")

main, side = ui.section()
with main:
    ui.numbers([(f"{bronze['rows'].sum():,}", "rows in bronze, as raw strings"),
                (f"{silver['rows'].sum():,}", "rows in the nine silver tables"),
                (f"{quarantined:,}", f"quarantined, {100 * quarantined / modelled:.4f}% of input")])
    dq = (silver[["entity", "rows"]]
          .merge(quarantine[["entity", "rows"]], on="entity", how="left",
                 suffixes=("_passed", "_quarantined"))
          .fillna({"rows_quarantined": 0}))
    bars = alt.Chart(dq).mark_bar(color=ui.palette()["series"][0], height=14).encode(
        x=alt.X("rows_passed:Q", title="rows in silver", axis=alt.Axis(format="~s")),
        y=alt.Y("entity:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("entity:N", title="table"),
                 alt.Tooltip("rows_passed:Q", title="passed", format=","),
                 alt.Tooltip("rows_quarantined:Q", title="quarantined", format=",")])
    labels = bars.mark_text(align="left", dx=6, fontSize=11).encode(
        text=alt.Text("rows_passed:Q", format=","))
    ui.figure((bars + labels).properties(height=28 * len(dq)), "1.1",
              "Rows in each silver table. Observations dominate, as they do in real records: "
              "every vital sign and lab result is one row.")
with side:
    failing = quarantine.loc[quarantine["rows"] > 0, "entity"].tolist()
    ui.notes("Bronze does nothing on purpose: every column is a string, so silver and gold "
             "can be rebuilt without uploading the raw files again.",
             f"Every quarantined row is in the {', '.join(failing) or 'no'} table; each keeps the "
             "rule it broke beside it.",
             "The rows come from two Synthea batches, 1,148 and 11,432 people, landed side "
             "by side without regenerating the first. <i>D65</i>",
             f"Counts captured {captured:%d %B %Y}. The app never queries the warehouse; it "
             "reads a published snapshot. <i>D36</i>")

with ui.method("The quality table"):
    dq["failure rate %"] = (100 * dq["rows_quarantined"]
                            / (dq["rows_passed"] + dq["rows_quarantined"])).round(4)
    ui.table(dq.astype({"rows_quarantined": int}))
    ui.table(bronze[["entity", "rows"]].rename(columns={"entity": "bronze file"}))

ui.pager(1)
