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


def test_care_gap_measures_are_known_labels():
    # gold_care_gap's only text column; a measure missing from ALLOWED_TEXT
    # would stop the publish.
    check_only_categories(pd.DataFrame({"measure": ["diabetes_hba1c", "bp_control",
                                                    "statin_therapy"], "gaps": [17, 58, 1]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"measure": ["statin_therapy", "Lucius"]}))


def test_story_labels_are_known_and_nothing_else_passes():
    check_only_categories(pd.DataFrame({
        "signal": ["age_band", "prior_stays_12m_band", "admit_year"],
        "level": ["80+", "2+", "2019"], "index_stays": [120, 60, 31]}))
    check_only_categories(pd.DataFrame({"decision": ["NO-GO"], "shortlisted": [1]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"signal": ["patient_id"]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"level": ["Lucius"]}))


def test_eval_labels_are_known_and_nothing_else_passes():
    check_only_categories(pd.DataFrame({
        "set_name": ["dev", "test"], "contestant": ["raw", "genie"],
        "verdict": ["correct", "answered_unanswerable"], "answers": [3, 1]}))
    with pytest.raises(SystemExit):
        check_only_categories(pd.DataFrame({"contestant": ["raw", "gpt"]}))
