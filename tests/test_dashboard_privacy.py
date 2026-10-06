"""Every number the dashboard shows goes through metrics.shown() (spec §5).

Reads the exported dashboard, so a widget added in the UI cannot skip the
rule unnoticed. Each dataset ends in `SELECT <items>` then `FROM final`
(plan P-d). Each item is a dimension name, or one shown() call.
"""
import json
import re
from pathlib import Path

import pytest

BOARD = Path(__file__).resolve().parents[1] / "dashboards/operations.lvdash.json"
SHOWN = "healthcare_dev.metrics.shown("
DIMENSIONS = {"payer", "hospital", "visit_type", "visit_month", "admit_quarter",
              "measure", "measure_year"}
# The filters each dataset must apply in its WHERE. A stay is always
# inpatient, so stays take no visit_type. Readmissions use D70's wide periods
# and care_gap has no hospital or payer, so those two take none (spec §4).
# The filter lists hold names only.
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


# Breakdowns shown beside their own total (the stays tile), so one hidden row
# would come back by subtraction: their numbers must read privacy_n, the
# protection-interval suppression (E61).
SECONDARY = {"by_payer"}
FILTER_LISTS = {"payers", "hospitals", "visit_types"}


def board() -> dict:
    return json.loads(BOARD.read_text(encoding="utf-8"))


def datasets() -> dict[str, str]:
    """Each dataset's SQL with `--` comments removed, so a comment cannot
    stand in for a filter."""
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
    """An aggregating widget (SUM over rows) would rebuild totals around the
    hidden cells; every widget reads the rows exactly as shown() left them."""
    aggregated = [w["widget"]["name"]
                  for page in board()["pages"] for w in page["layout"]
                  for q in w["widget"].get("queries", [])
                  if q["query"].get("fields") and q["query"]["datasetName"] not in FILTER_LISTS
                  and not q["query"].get("disaggregated")]
    assert not aggregated, f"widgets aggregate shown() values: {aggregated}"
