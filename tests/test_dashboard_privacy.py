"""Every number the exported dashboard shows goes through metrics.shown()."""
import json
import re
from pathlib import Path

import pytest

BOARD = Path(__file__).resolve().parents[1] / "dashboards/operations.lvdash.json"
SHOWN = "healthcare_dev.metrics.shown("
DIMENSIONS = {"payer", "hospital", "visit_type", "visit_month", "admit_quarter",
              "measure", "measure_year"}
# Filters each dataset's WHERE must apply (stays: no visit_type; readmission and care_gap: none).
PARAMS = {
    "payers": set(), "hospitals": set(), "visit_types": set(),
    "kpi_visits": {"payer", "hospital", "visit_type"},
    "visits_trend": {"payer", "hospital", "visit_type"},
    "kpi_stays": {"payer", "hospital"},
    "stays_trend": {"payer", "hospital"},
    "by_payer": {"payer", "hospital"},
    "by_hospital": {"payer", "hospital"},
    "kpi_readmission": set(),
    "care_gaps": set(),
}


def final_items(sql: str) -> list[str]:
    """The items of the last `SELECT ... FROM final`, split on top-level commas."""
    head = sql.rsplit("\nFROM final", 1)[0]
    text = head.rsplit("\nSELECT ", 1)[1]
    items, depth, current = [], 0, ""
    for char in text:
        if char == "," and depth == 0:
            items.append(current.strip())
            current = ""
            continue
        depth += (char == "(") - (char == ")")
        current += char
    items.append(current.strip())
    return items


def is_safe(item: str) -> bool:
    """A dimension name, or `shown(...) AS name` with nothing outside the call."""
    if item in DIMENSIONS:
        return True
    match = re.fullmatch(r"(.*\))\s+AS\s+\w+", item, flags=re.S)
    if not match or not match[1].startswith(SHOWN):
        return False
    call, depth = match[1], 0
    for i, char in enumerate(call):
        depth += (char == "(") - (char == ")")
        if depth == 0 and char == ")":
            return i == len(call) - 1     # the first call closes at the very end
    return False


# Breakdowns beside their total must use privacy_n, or subtraction gives a hidden row back (E61).
SECONDARY = {"by_payer"}
FILTER_LISTS = {"payers", "hospitals", "visit_types"}


def board() -> dict:
    return json.loads(BOARD.read_text(encoding="utf-8"))


def datasets() -> dict[str, str]:
    """Each dataset's SQL without `--` comments, so a comment can't stand in for a filter."""
    return {d["displayName"]: re.sub(r"--[^\n]*", "",
                                     "".join(d.get("queryLines") or [d.get("query", "")]))
            for d in board()["datasets"]}


def after_final(sql: str) -> str:
    return sql.rsplit("\nFROM final", 1)[1]


def test_final_items_split_on_top_level_commas():
    sql = "WITH final AS (SELECT 1)\nSELECT payer,\n       x.shown(a, b) AS c\nFROM final"
    assert final_items(sql) == ["payer", "x.shown(a, b) AS c"]


@pytest.mark.parametrize("item, safe", [
    ("payer", True),
    ("healthcare_dev.metrics.shown(stays, stays) AS stays", True),
    ("healthcare_dev.metrics.shown(stays, healthcare_dev.metrics.shown(p, x - y)) AS c", True),
    ("stays", False),                                                    # a bare measure
    ("MEASURE(stays) AS stays", False),
    ("healthcare_dev.metrics.shown(stays, stays) + prior AS s", False),  # math outside the call
    ("round(healthcare_dev.metrics.shown(stays, los), 1) AS los", False),
])
def test_is_safe(item, safe):
    assert is_safe(item) is safe


def test_every_dataset_is_known():
    assert set(datasets()) == set(PARAMS), \
        "a dataset was added or renamed: decide its filters in PARAMS"


@pytest.mark.parametrize("name", sorted(PARAMS))
def test_dataset_hides_small_cells(name):
    sql = datasets()[name]
    unsafe = [i for i in final_items(sql) if not is_safe(i)]
    assert not unsafe, f"{name} returns numbers outside shown(): {unsafe}"
    missing = {p for p in PARAMS[name] if f":{p}" not in sql}
    assert not missing, f"{name} does not filter on {sorted(missing)}"
    # Only WHERE / ORDER BY may follow: a wrapping query would escape the check.
    assert not re.search(r"\b(SELECT|FROM|JOIN|UNION)\b", after_final(sql), flags=re.I), \
        f"{name} has a query after FROM final"
    if name in SECONDARY:
        numbers = [i for i in final_items(sql) if i not in DIMENSIONS]
        assert all(i.startswith(SHOWN + "privacy_n,") for i in numbers), \
            f"{name} lost its secondary suppression"


def test_widgets_show_rows_as_returned():
    """No aggregating widget: summing rows would rebuild totals around hidden cells."""
    aggregated = [w["widget"]["name"]
                  for page in board()["pages"] for w in page["layout"]
                  for q in w["widget"].get("queries", [])
                  if q["query"].get("fields") and q["query"]["datasetName"] not in FILTER_LISTS
                  and not q["query"].get("disaggregated")]
    assert not aggregated, f"widgets aggregate shown() values: {aggregated}"
