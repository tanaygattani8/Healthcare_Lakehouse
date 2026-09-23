from pyspark import pipelines as dlt
from pyspark.sql.functions import col, current_timestamp, lit, regexp_extract

LANDING_PATH = spark.conf.get("landing_path")
BATCH_ID = spark.conf.get("batch_id", "manual")


@dlt.table(
    name="br_notes",
    comment="One row per clinical note, text kept exactly as written.",
    table_properties={"quality": "bronze"},
)
def br_notes():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "text")
        # Without this every LINE becomes a row. We want one row per FILE.
        .option("wholetext", "true")
        .option("cloudFiles.schemaLocation", f"{LANDING_PATH}/_schema/notes")
        .load(f"{LANDING_PATH}/notes/")
        .select(
            # ..._c9d1202b-ceba-842a-6d88-85aab58fe1cd.txt -> the uuid
            regexp_extract(
                col("_metadata.file_path"), r"([0-9a-f-]{36})\.txt$", 1
            ).alias("patient_id"),
            col("value").alias("note_text"),
            col("_metadata.file_path").alias("_source_file"),
            current_timestamp().alias("_ingested_at"),
            lit(BATCH_ID).alias("_batch_id"),
        )
    )