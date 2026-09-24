from scripts.detect_ner import merge


def test_fragments_of_one_name_become_one_span():
    # 'Luc' + 'ius' + ' ' + 'Emard', then an unrelated date
    tokens = [(0, 3, "name"), (3, 6, "name"), (7, 12, "name"), (20, 30, "date")]
    assert merge(tokens) == [(0, 12, "name"), (20, 30, "date")]


def test_repeats_from_overlapping_pieces_collapse():
    assert merge([(0, 6, "name"), (3, 6, "name"), (0, 6, "name")]) == [(0, 6, "name")]


def test_different_kinds_side_by_side_stay_apart():
    assert merge([(0, 6, "name"), (7, 17, "date")]) == [(0, 6, "name"), (7, 17, "date")]
