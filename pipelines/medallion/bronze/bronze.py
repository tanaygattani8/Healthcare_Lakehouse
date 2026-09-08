from pyspark import pipelines as dlt
from pyspark.sql.functions import col, current_timestamp, lit

ENTITIES = [
    "patients", "encounters", "conditions", "medications",
    "observations", "procedures", "immunizations", "allergies", "careplans",
    "organizations", "providers", "payers"
]

LANDING_PATH = spark.conf.get("landing_path")
BATCH_ID = spark.conf.get("batch_id", "manual")

def make_bronze_table(entity: str) -> None:
    @dlt.table(
        name=f"br_{entity}",
        comment=f"Raw Synthea {entity}, exactly as landed. No Transformation.",
        table_properties={"quality": "bronze"}
    )
    def _bronze(): 
        return (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "csv")
            .option("cloudFiles.inferColumnTypes", "false")
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .option("cloudFiles.schemaLocation", f"{LANDING_PATH}/_schema/{entity}")
            .option("header", "true")
            # A directory, not a file — Auto Loader watches folders. One per
            # entity so each stream sees only its own data.
            .load(f"{LANDING_PATH}/csv/{entity}/")
            .select(
                "*",
                col("_metadata.file_path").alias("_source_file"),
                current_timestamp().alias("_ingested_at"),
                lit(BATCH_ID).alias("_batch_id"),
            )
        )

for _entity in ENTITIES:
    make_bronze_table(_entity)