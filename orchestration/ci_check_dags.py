"""CI: the DAGs load in the real Airflow image, and are exactly the expected ones."""

import sys

# Airflow 3.3's DagBag has no include_examples; examples would fail the id check anyway.
from airflow.dag_processing.dagbag import DagBag

# A new DAG joins this set in the same change, or CI goes red.
EXPECTED = {"medallion", "retrain"}

bag = DagBag("/opt/airflow/dags")
for path, error in bag.import_errors.items():
    print(f"IMPORT ERROR in {path}:\n{error}")
print("dags:", sorted(bag.dag_ids))
if bag.import_errors or set(bag.dag_ids) != EXPECTED:
    sys.exit(f"expected exactly {sorted(EXPECTED)} and no import errors")
print("ok")
