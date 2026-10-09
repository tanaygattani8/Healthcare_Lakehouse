-- Phase 5: scores by tier and every failure; set run_id in both statements.

SELECT contestant, tier,
       count_if(verdict = 'correct') AS correct, count(*) AS asked
FROM healthcare_dev.ops.eval_run
WHERE run_id = 'dev-1'
GROUP BY ALL ORDER BY contestant, tier;

SELECT question_id, contestant, verdict, error, generated_sql
FROM healthcare_dev.ops.eval_run
WHERE run_id = 'dev-1' AND verdict <> 'correct'
ORDER BY question_id, contestant;
