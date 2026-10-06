-- Phase 8's proof that moving stay cost and length of stay into
-- readmission_events changed nothing else. Every count must be 0.

-- readmission_events, without its phase 8 columns, against the PySpark build.
SELECT
  (SELECT count(*) FROM (SELECT * EXCEPT (key_copies, organization_id, payer_id, length_of_stay_days, stay_claim_cost) FROM healthcare_dev.gold.readmission_events
                         EXCEPT ALL
                         SELECT * FROM healthcare_dev.ops.pyspark_readmission_events)) AS events_only_in_gold,
  (SELECT count(*) FROM (SELECT * FROM healthcare_dev.ops.pyspark_readmission_events
                         EXCEPT ALL
                         SELECT * EXCEPT (key_copies, organization_id, payer_id, length_of_stay_days, stay_claim_cost) FROM healthcare_dev.gold.readmission_events)) AS events_only_in_pyspark;

-- readmission_signals, the model's table, against its copy from before.
-- ops.signals_before is dropped by sql/phase8_cleanup.sql once this reads
-- 0, so this query is a record of phase 8 and fails if rerun.
SELECT
  (SELECT count(*) FROM (SELECT * FROM healthcare_dev.gold.readmission_signals
                         EXCEPT ALL
                         SELECT * FROM healthcare_dev.ops.signals_before)) AS signals_only_now,
  (SELECT count(*) FROM (SELECT * FROM healthcare_dev.ops.signals_before
                         EXCEPT ALL
                         SELECT * FROM healthcare_dev.gold.readmission_signals)) AS signals_only_before;