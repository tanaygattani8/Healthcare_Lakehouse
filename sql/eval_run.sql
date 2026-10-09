-- Phase 5: one verdict per contestant, question and run; never result values.
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
