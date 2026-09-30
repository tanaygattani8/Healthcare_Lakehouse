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


G = "healthcare_dev.gold.patient_360"


@pytest.mark.parametrize("sql", [
    f"SELECT s.* FROM {G} p, silver.patient s",
    f"SELECT s.* FROM {G} p, ops.deid_key s",
    f"SELECT s.* FROM {G} p, `healthcare_dev`.`silver`.`patient` s",
    f"SELECT * FROM {G} p, parquet.`/Volumes/healthcare_dev/bronze/landing/x` s",
    f"SELECT * FROM {G} p, hive_metastore.default.t",
    f"SELECT * FROM {G} p, IDENTIFIER('sil' || 'ver.patient')",
    f"SELECT * FROM {G} p, table_changes('x', 0)",
    "SELECT * FROM /*x*/ healthcare_dev.silver.patient",
    "SELECT * FROM (SELECT * FROM healthcare_dev.silver.patient) t",
    f"SELECT (SELECT max(FIRST) FROM healthcare_dev.silver.patient) AS n FROM {G}",
    "INSERT INTO healthcare_dev.gold.x SELECT 1",
    "SELECT FROM WHERE",
])
def test_blocked_by_parser_allow_list(sql):
    assert problem(sql) is not None


@pytest.mark.parametrize("sql", [
    f"-- count patients\nSELECT count(*) FROM {G}",
    "SELECT EXTRACT(YEAR FROM CAST(started_at AS DATE)) AS y "
    "FROM healthcare_dev.gold.fact_encounter",
    "SELECT count(*) FROM healthcare_dev.gold.readmission_events "
    "WHERE admit_reason IS DISTINCT FROM 'x'",
    "SELECT count(*) FROM healthcare_dev.gold.readmission_events "
    "WHERE admit_reason LIKE '%discharged from hospital%'",
    "SELECT count(*) FROM healthcare_dev.gold.readmission_events "
    "WHERE admit_reason = 'x;y'",
    f"SELECT count(*) FROM {G}; -- done",
    "WITH a(x) AS (SELECT 1) SELECT x FROM a",
    "SELECT e FROM healthcare_dev.gold.fact_encounter "
    "LATERAL VIEW explode(array(1, 2)) t AS e",
    f"SELECT gender FROM {G} UNION ALL "
    "SELECT encounter_class FROM healthcare_dev.gold.fact_encounter",
    "SELECT `gender`, count(*) FROM `healthcare_dev`.`gold`.`patient_360` GROUP BY `gender`",
])
def test_allowed_by_parser_allow_list(sql):
    assert problem(sql) is None
