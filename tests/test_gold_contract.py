import re
from pathlib import Path

from scripts import readmission_model as rm

SQL = Path(__file__).resolve().parents[1] / "pipelines/medallion/gold/readmission_signals.sql"
# Types readmission_signals uses; add any new type here.
TYPES = r"STRING|INT|BIGINT|SMALLINT|TINYINT|DOUBLE|FLOAT|BOOLEAN|DATE|TIMESTAMP|DECIMAL"
# What the model reads beyond FEATURES: target, keys, split dates, population flag.
MODEL_READS = set(rm.FEATURES) | {rm.TARGET, "patient_id", "stay_no", "first_encounter_id",
                                  "admit_day",
                                  "discharge_day", "had_bypass_surgery"}


def declared_columns(sql: str) -> list[str]:
    """Column names in the CREATE's typed list, i.e. before the COMMENT line."""
    head = sql.split("\nCOMMENT", 1)[0]
    return re.findall(rf"^\s*([a-z_0-9]+)\s+(?:{TYPES})\b", head, flags=re.M)


def test_declared_columns_reads_a_typed_list():
    sql = ("CREATE OR REFRESH MATERIALIZED VIEW x.gold.t (\n"
           "    patient_id STRING,\n"
           "    cost DECIMAL(24,2),\n"
           "    CONSTRAINT ok EXPECT (cost IS NOT NULL) ON VIOLATION FAIL UPDATE\n"
           ")\nCOMMENT \"c\"\nAS SELECT age INT_VALUE FROM y")
    assert declared_columns(sql) == ["patient_id", "cost"]


def test_every_column_the_model_reads_is_declared():
    missing = MODEL_READS - set(declared_columns(SQL.read_text(encoding="utf-8")))
    assert not missing, f"readmission_signals no longer declares {sorted(missing)}"