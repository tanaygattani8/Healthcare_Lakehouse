"""The three copies of the entity list must match (D4, E15)."""

import re
from pathlib import Path

from scripts.entities import ENTITIES

ROOT = Path(__file__).resolve().parent.parent


def _quoted_names(text: str, start: str, end: str) -> list[str]:
    """Entity names in the list literal between `start` and the next `end`."""
    body = text.split(start, 1)[1]
    return re.findall(r'"([a-z_]+)"', body[: body.index(end)])


def test_upload_script_lists_the_same_entities():
    names = _quoted_names((ROOT / "scripts" / "upload.ps1").read_text(), "$entities = @(", ")")

    assert names == ENTITIES


def test_bronze_pipeline_lists_the_same_entities():
    names = _quoted_names(
        (ROOT / "pipelines" / "medallion" / "bronze" / "bronze.py").read_text(),
        "ENTITIES = [",
        "]",
    )

    assert names == ENTITIES
