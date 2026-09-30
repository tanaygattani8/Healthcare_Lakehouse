import pytest

from scripts.eval_questions import check_frozen, fingerprint, load

GOOD = """
- id: a1
  tier: 1
  question: How many patients are there?
  answer_sql: SELECT count(*) FROM healthcare_dev.gold.patient_360
- id: a2
  tier: 4
  question: What is the oldest patient's name?
"""


def write(tmp_path, text, name="q.yaml"):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


def test_loads_questions_in_order(tmp_path):
    questions = load(write(tmp_path, GOOD))
    assert [q.id for q in questions] == ["a1", "a2"]
    assert questions[0].answerable and not questions[1].answerable
    assert questions[0].ordered is False


def test_duplicate_id_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        load(write(tmp_path, GOOD.replace("id: a2", "id: a1")))


def test_answerable_question_needs_answer_sql(tmp_path):
    with pytest.raises(SystemExit):
        load(write(tmp_path, GOOD.replace(
            "  answer_sql: SELECT count(*) FROM healthcare_dev.gold.patient_360\n", "")))


def test_should_refuse_question_must_not_have_answer_sql(tmp_path):
    with pytest.raises(SystemExit):
        load(write(tmp_path, GOOD + "  answer_sql: SELECT 1\n"))


def test_fingerprint_ignores_line_endings(tmp_path):
    unix = write(tmp_path, GOOD, "unix.yaml")
    windows = write(tmp_path, GOOD.replace("\n", "\r\n"), "windows.yaml")
    assert fingerprint(unix) == fingerprint(windows)


def test_edited_test_set_is_refused(tmp_path):
    path = write(tmp_path, GOOD)
    sha = tmp_path / "q.sha256"
    sha.write_text(fingerprint(path) + "\n", encoding="utf-8")
    check_frozen(path, sha)                                   # unchanged: passes
    write(tmp_path, GOOD.replace("patients", "people"))
    with pytest.raises(SystemExit):
        check_frozen(path, sha)
