"""Throwaway. Task 0 of phase 2a: can one pipeline publish to a second schema?

Delete this file, its libraries entry, and both tables once the answer is
recorded. Two tables rather than one so a failure says which half broke:
writing to another schema, or reading across schemas.
"""

from pyspark import pipelines as dlt

CATALOG = spark.conf.get("catalog")


@dlt.table(name=f"{CATALOG}.silver.sp_write_target")
def sp_write_target():
    # Depends on nothing. If this lands in silver, fully-qualified names work.
    return spark.range(1).selectExpr("'ok' AS spike")


@dlt.table(name=f"{CATALOG}.silver.sp_read_bronze")
def sp_read_bronze():
    # Reads across schemas, which every silver table will do.
    return spark.read.table(f"{CATALOG}.bronze.br_patients").selectExpr("count(*) AS n")
