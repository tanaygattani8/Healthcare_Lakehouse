from scripts.build_answer_key import DATE_SHAPE, date_forms


def test_the_one_pass_search_finds_every_form_date_forms_produces():
    # If a form is added to date_forms() but not to DATE_SHAPE, that form is
    # silently never found and every program is marked wrong on it for ever.
    for value in ["1971-05-01", "1999-12-11"]:
        for form in date_forms(value):
            note = f"Seen on {form}. Next visit pending."
            assert [m.group() for m in DATE_SHAPE.finditer(note)] == [form]


def test_a_date_glued_to_other_characters_is_not_a_date():
    assert not DATE_SHAPE.search("1971-05-01T10:00")
    assert not DATE_SHAPE.search("x5/1/1971")
