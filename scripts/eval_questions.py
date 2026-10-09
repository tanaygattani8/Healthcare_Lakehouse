"""Load and validate eval question files and prove the test set unedited; tier 4 must refuse."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Question:
    id: str
    tier: int
    question: str
    answer_sql: str | None = None
    ordered: bool = False

    @property
    def answerable(self) -> bool:
        return self.tier != 4


def load(path: Path) -> list[Question]:
    items = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    questions: list[Question] = []
    seen: set[str] = set()
    for item in items:
        q = Question(**item)
        if q.id in seen:
            raise SystemExit(f"{path}: duplicate id {q.id}")
        if q.tier not in (1, 2, 3, 4):
            raise SystemExit(f"{path}: {q.id} has tier {q.tier}; tiers are 1-4")
        if q.answerable and not q.answer_sql:
            raise SystemExit(f"{path}: {q.id} is tier {q.tier} but has no answer_sql")
        if not q.answerable and q.answer_sql:
            raise SystemExit(f"{path}: {q.id} is tier 4 (should refuse) but has answer_sql")
        seen.add(q.id)
        questions.append(q)
    return questions


def fingerprint(path: Path) -> str:
    # Normalise line endings: a CRLF checkout is not an edit.
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_frozen(path: Path, sha_path: Path) -> None:
    frozen = Path(sha_path).read_text(encoding="utf-8").split()[0]
    if fingerprint(path) != frozen:
        raise SystemExit(f"{path} has changed since it was frozen ({sha_path}). "
                         "The test set is run as written, or not at all.")
