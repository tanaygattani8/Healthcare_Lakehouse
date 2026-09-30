from scripts.eval_text_to_sql import scrub


def test_error_class_only():
    assert scrub("[CAST_INVALID_INPUT] The value 'Smith' cannot be cast") == "[CAST_INVALID_INPUT]"


def test_literals_and_numbers_masked():
    out = scrub("""Invalid value "4500" near 'Jane' on 2024-01-05""")
    assert not any(s in out for s in ("4500", "Jane", "2024"))


def test_first_line_only():
    assert scrub("first line\nsecond line") == "first line"
