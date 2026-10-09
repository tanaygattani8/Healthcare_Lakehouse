"""The DAG's PHI gate and governance_check.sql's CHECK 3 must list the same columns (D81)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def phi_rules(text: str) -> tuple[list[str], list[str]]:
    """The identifier column names, and the table-name exclusions, of CHECK 3."""
    names = re.search(r"upper\(c\.column_name\) IN \((.*?)\)", text, re.S).group(1)
    skips = re.findall(r"c\.table_name NOT R?LIKE\s+'([^']*)'", text)
    return re.findall(r"'([A-Z_]+)'", names), skips


def test_the_dag_gate_and_governance_check_agree():
    check = (ROOT / "sql/governance_check.sql").read_text(encoding="utf-8")
    dag = (ROOT / "orchestration/dags/medallion.py").read_text(encoding="utf-8")
    names, skips = phi_rules(check.split("-- CHECK 3")[1])
    assert len(names) == 23 and len(skips) == 2
    dag_names, dag_skips = phi_rules(dag)
    assert dag_names == names
    # The DAG holds the SQL in a Python string, so its backslashes are doubled.
    assert [s.replace("\\\\", "\\") for s in dag_skips] == skips
