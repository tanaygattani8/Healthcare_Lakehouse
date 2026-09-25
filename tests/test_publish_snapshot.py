import pandas as pd
import pytest

from scripts.publish_snapshot import check_only_categories


def test_counts_and_known_labels_pass():
    check_only_categories(pd.DataFrame({"stage": ["llm"], "phi_category": ["name"],
                                        "recall": [0.996]}))


def test_a_name_in_any_text_column_is_refused():
    # The failure this exists for: a join mistake that carries surface_text,
    # or a label column that picked up a real value.
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"stage": ["llm"], "phi_category": ["Lucius"]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"surface_text": ["Lucius"]}))
