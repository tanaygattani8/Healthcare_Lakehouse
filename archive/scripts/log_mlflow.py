"""Log ops.detection_score per detection program as an MLflow run (needs mlflow-skinny)."""

from __future__ import annotations

import sys

import mlflow

from scripts import dbx

# How each program ran. Measured, not planned (decision.md D53).
SETUP = {
    "roster": {"method": "look up the patient's own details and search",
               "where": "local script, loaded by SQL"},
    "regex": {"method": "patterns, no patient list", "where": "laptop"},
    "ner": {"method": "obi/deid_roberta_i2b2, 512-token windows, stride 64",
            "where": "laptop CPU", "seconds_per_piece": 4.49},
    "llm": {"method": "databricks-meta-llama-3-3-70b-instruct via ai_query, temperature 0",
            "where": "Databricks, one statement per patient", "bad_json_replies": 24,
            "text_not_in_note_replies": 34},
}


def main() -> None:
    # MLflow prints an emoji the Windows console can't encode, mid-run.
    sys.stdout.reconfigure(encoding="utf-8")
    with dbx.connect() as conn, conn.cursor() as cur:   # also loads .env for mlflow
        cur.execute("SELECT current_user()")
        user = cur.fetchone()[0]
        cur.execute("""SELECT stage, phi_category, real_items, guesses, precision,
                              recall, covered_recall, exact_recall
                       FROM healthcare_dev.ops.detection_score""")
        rows = cur.fetchall()

    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment(f"/Users/{user}/phase3b-phi-detection")

    for stage, setup in SETUP.items():
        with mlflow.start_run(run_name=stage):
            mlflow.log_params({"piece_chars": 2000, "piece_step": 1800,
                               "test_patients": 25, "match_rule": "same kind, overlap",
                               **setup})
            for r in (r for r in rows if r.stage == stage):
                mlflow.log_metric(f"guesses_{r.phi_category}", r.guesses)
                mlflow.log_metric(f"precision_{r.phi_category}", r.precision)
                # No real items means no recall; precision 0 already says it.
                if r.real_items is not None:
                    mlflow.log_metric(f"recall_{r.phi_category}", r.recall)
                    mlflow.log_metric(f"covered_recall_{r.phi_category}", r.covered_recall)
                    mlflow.log_metric(f"exact_recall_{r.phi_category}", r.exact_recall)
        print(f"logged {stage}")


if __name__ == "__main__":
    main()
