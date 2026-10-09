-- Row count and hash sum of the ML tables phase 9 must leave alone; scored_at left out.
SELECT 'drift_report' AS t, count(*) AS rows, sum(cast(xxhash64(*) AS DECIMAL(38, 0))) AS fingerprint FROM healthcare_dev.ml.drift_report
UNION ALL SELECT 'readmission_scores', count(*), sum(cast(xxhash64(* EXCEPT (scored_at)) AS DECIMAL(38, 0))) FROM healthcare_dev.ml.readmission_scores
ORDER BY t;
