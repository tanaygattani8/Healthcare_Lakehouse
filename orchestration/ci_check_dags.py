"""CI: the Airflow DAGs load in the real image (phase 10, spec §3.3).

Runs inside the image built from orchestration/Dockerfile, with dags/
mounted at /opt/airflow/dags. Lives beside dags/, not in it: Airflow parses
every file in dags/ as a possible DAG. Exits non-zero on any import error,
or if the DAGs are not exactly the ones this repo checks.
"""

import sys

# Airflow 3.3 keeps DagBag here, and it no longer takes include_examples:
# example DAGs would show up in dag_ids below and fail the check anyway.
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
