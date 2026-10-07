"""Streamlit deploys the app with app/requirements.txt; CI tests with the
root requirements.txt. Every app pin must be the root's pin, or CI tests a
different stack from the one that ships (phase 10; the note after D26)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pins(path: Path) -> dict[str, str]:
    """Package name (lower case, - _ . alike) to its specifier, '' if unpinned."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            name, spec = re.match(r"([A-Za-z0-9_.-]+)(.*)", line).groups()
            found[re.sub(r"[-_.]+", "-", name.lower())] = spec.replace(" ", "")
    return found


def test_pins_reads_names_and_specifiers():
    assert pins(ROOT / "app/requirements.txt")["streamlit"].startswith("==")


def test_every_app_pin_is_the_projects_pin():
    app, project = pins(ROOT / "app/requirements.txt"), pins(ROOT / "requirements.txt")
    wrong = {name: {"app": spec, "root": project.get(name)}
             for name, spec in app.items() if project.get(name) != spec}
    assert not wrong, f"app/requirements.txt disagrees with requirements.txt: {wrong}"
