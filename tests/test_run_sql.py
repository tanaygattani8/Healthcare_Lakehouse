from scripts.run_sql import _statements


def test_semicolon_in_a_comment_does_not_split_the_statement():
    # The bug this exists for: a naive split on ';' cut the prose in half and
    # sent "after tagging it would orphan them." to the warehouse as SQL.
    sql = """
-- Safe to run now; after tagging it would orphan them.
ALTER GOVERNED TAG phi_category SET VALUES ('name', 'date');
"""
    assert _statements(sql) == [
        "-- Safe to run now; after tagging it would orphan them.\n"
        "ALTER GOVERNED TAG phi_category SET VALUES ('name', 'date')"
    ]


def test_trailing_comment_is_not_sent_as_a_statement():
    sql = "DROP TABLE t;\n-- deliberately not dropping the governed tag\n"
    assert _statements(sql) == ["DROP TABLE t"]


def test_statements_split_on_real_terminators():
    assert _statements("SELECT 1;\nSELECT 2;\n") == ["SELECT 1", "SELECT 2"]


def test_semicolon_inside_a_string_literal_does_not_split():
    # A COMMENT written in English is prose, and prose has semicolons in it.
    sql = (
        "CREATE TABLE t COMMENT 'chosen early; cut later' AS SELECT 1;\n"
        "SELECT 2;\n"
    )
    assert _statements(sql) == [
        "CREATE TABLE t COMMENT 'chosen early; cut later' AS SELECT 1",
        "SELECT 2",
    ]


def test_escaped_quote_inside_a_string_is_not_the_end_of_it():
    sql = "SELECT 'it''s here; really' AS a;\nSELECT 2;\n"
    assert _statements(sql) == ["SELECT 'it''s here; really' AS a", "SELECT 2"]


def test_a_comment_after_code_on_the_same_line_still_terminates():
    # The semicolon inside the trailing comment must not split anything. The
    # comment itself rides along with the next statement, which is deliberate:
    # run_sql prints a statement's first line as its label, and a leading
    # comment is a better label than the SQL.
    sql = "SELECT 1;  -- trailing note; with a semicolon\nSELECT 2;\n"
    assert _statements(sql) == [
        "SELECT 1",
        "-- trailing note; with a semicolon\nSELECT 2",
    ]


def test_semicolon_inside_a_double_quoted_comment_does_not_split():
    # This project writes table comments as COMMENT "..." — double quotes.
    sql = 'CREATE TABLE t COMMENT "chosen early; cut later" AS SELECT 1;\nSELECT 2;\n'
    assert _statements(sql) == [
        'CREATE TABLE t COMMENT "chosen early; cut later" AS SELECT 1',
        "SELECT 2",
    ]
