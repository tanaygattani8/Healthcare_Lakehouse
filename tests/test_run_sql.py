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
