import pytest

from scripts.sql_gate import problem

GOLD = "SELECT count(*) FROM healthcare_dev.gold.patient_360"


def test_plain_gold_select_is_allowed():
    assert problem(GOLD) is None
    assert problem(GOLD + ";") is None


def test_metric_view_with_a_cte_is_allowed():
    assert problem("WITH r AS (SELECT MEASURE(index_stays) AS n "
                   "FROM healthcare_dev.metrics.readmission) SELECT n FROM r") is None


def test_extract_from_is_not_a_table():
    assert problem("SELECT EXTRACT(YEAR FROM started_at) AS y "
                   "FROM healthcare_dev.gold.fact_encounter") is None


@pytest.mark.parametrize("sql", [
    "DROP TABLE healthcare_dev.gold.patient_360",
    GOLD + "; DROP TABLE healthcare_dev.gold.patient_360",
    GOLD + " -- ;\nDROP TABLE healthcare_dev.gold.patient_360",
    "SELECT FIRST FROM healthcare_dev.silver.patient",
    "SELECT * FROM healthcare_dev.ops.deid_key",
    "SELECT * FROM patient_360",
    "SELECT * FROM healthcare_dev.gold.patient_360 p, healthcare_dev.silver.patient s",
    "SELECT ai_query('m', 'x') FROM healthcare_dev.gold.patient_360",
    "SELECT * FROM read_files('/Volumes/healthcare_dev/bronze/landing/')",
    "SELECT * FROM system.billing.usage",
])
def test_blocked(sql):
    assert problem(sql) is not None
