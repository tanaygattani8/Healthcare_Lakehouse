-- Phase 5: one row per contestant per question per run. Verdicts only:
-- no result values are ever stored (spec §4).
CREATE TABLE IF NOT EXISTS healthcare_dev.ops.eval_run (
    run_id         STRING,
    set_name       STRING,
    contestant     STRING,
    question_id    STRING,
    tier           INT,
    generated_sql  STRING,
    verdict        STRING,
    error          STRING,
    seconds        DOUBLE,
    run_at         TIMESTAMP
)
COMMENT "Text-to-SQL eval: one verdict per contestant per question per run. No result values.";
