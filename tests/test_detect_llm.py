from scripts.detect_llm import spans_for

PIECE = "Lucius is a 50 year-old. Seen 2011-03-04. Lucius returned 2011-03-04."


def test_every_occurrence_is_found_not_just_the_first():
    reply = '[{"text": "Lucius", "category": "name"}]'
    found, how = spans_for(PIECE, reply)
    assert how == "ok"
    second = PIECE.index("Lucius", 1)
    assert [(s, e) for s, e, _, _ in found] == [(0, 6), (second, second + 6)]


def test_chatter_around_the_json_is_ignored_and_aliases_are_mapped():
    reply = 'Sure! Here it is:\n[{"text": "2011-03-04", "category": "Date"}, ' \
            '{"text": "Lucius", "category": "person"}]\nHope that helps.'
    found, how = spans_for(PIECE, reply)
    assert how == "ok"
    assert {c for _, _, c, _ in found} == {"date", "name"}
    assert len(found) == 4


def test_text_the_model_invented_is_reported_not_silently_dropped():
    found, how = spans_for(PIECE, '[{"text": "Lucius Emard", "category": "name"}]')
    assert (found, how) == ([], "not_in_note")


def test_a_reply_that_is_not_json_is_reported():
    assert spans_for(PIECE, "I cannot help with that.") == ([], "bad_json")
    assert spans_for(PIECE, "[{broken") == ([], "bad_json")


def test_short_names_are_kept():
    found, _ = spans_for("Al was seen.", '[{"text": "Al", "category": "name"}]')
    assert [(s, e) for s, e, _, _ in found] == [(0, 2)]
