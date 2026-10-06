-- Row count and a hash sum for the ML tables phase 9 must leave alone until
-- its live run (spec §7). scored_at is left out: rerunning the scoring
-- writes the same rows with a new timestamp (Task 4 does exactly that).
-- The cast avoids the 64-bit overflow, as in gold_fingerprint.sql.
SELECT 'drift_report' AS t, count(*) AS rows, sum(cast(xxhash64(*) AS DECIMAL(38, 0))) AS fingerprint FROM healthcare_dev.ml.drift_report
UNION ALL SELECT 'readmission_scores', count(*), sum(cast(xxhash64(* EXCEPT (scored_at)) AS DECIMAL(38, 0))) FROM healthcare_dev.ml.readmission_scores
ORDER BY t;
