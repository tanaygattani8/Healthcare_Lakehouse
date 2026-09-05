"""The entity list is deliberately duplicated in three places (decision D4).

`bronze.py` runs inside a Lakeflow pipeline where importing from the repo root
is version-dependent friction, and `upload.ps1` is PowerShell, so neither can
import `scripts/entities.py`. Duplication is the right call — but it was trusted
rather than enforced, and `immunizations` silently vanished from the upload list
once already (E15). Nothing failed; the file just never landed, and the empty
bronze table would have surfaced two tasks downstream as an Auto Loader problem.

This test is the enforcement D21 deferred until the third copy existed.
"""

import re
from pathlib import Path

from scripts.entities import ENTITIES

ROOT = Path(__file__).resolve().parent.parent


def _quoted_names(text: str, start: str, end: str) -> list[str]:
    """Entity names from the list literal between `start` and the next `end`.

    `end` is explicit because PowerShell closes with ")" and Python with "]".
    Getting it wrong reads past the list and silently picks up every other
    lowercase string in the file, which is how the first version of this test
    "failed" against a bronze.py that was perfectly correct.
    """
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
