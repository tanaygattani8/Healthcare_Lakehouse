"""kanon.sql's released k must group on every column deid.patient publishes (E72)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Not birth, death or gender, which are what D56 takes an outsider to know.
NOT_QUASI = {"deid_id", "race", "ethnicity", "marital", "state"}


def published_columns() -> set[str]:
    sql = (ROOT / "sql/deid.sql").read_text(encoding="utf-8")
    body = sql.split("CREATE OR REPLACE TABLE healthcare_dev.deid.patient")[1]
    select = re.search(r"\)\s*SELECT (.*?)\nFROM counted", body, re.S).group(1)
    select = re.sub(r"--[^\n]*", "", select)
    return {re.split(r"\s+AS\s+|\s+", item.strip())[-1] for item in select.split(",")}


def test_released_k_groups_on_every_published_quasi_identifier():
    kanon = (ROOT / "sql/kanon.sql").read_text(encoding="utf-8")
    grouped = re.search(r"released AS \(.*?GROUP BY ([^\n]*)", kanon, re.S).group(1)
    published = published_columns()
    assert {"birth_year_from", "years_suppressed", "is_deceased", "gender"} <= published
    assert published - NOT_QUASI <= {c.strip() for c in grouped.split(",")}
