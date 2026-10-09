-- Phase 7's proof for the two tables that went wrong mid-phase (E58, E59),
-- beyond the fingerprint. Every count must be 0. A record of phase 7:
-- readmission_events gained four columns in phase 8, so the current form of
-- the events proof is archive/sql/phase8_proof.sql.

-- readmission_events: E58's fix restored it (its fingerprint matches the
-- before-record); this also proves it against the independent PySpark build.
SELECT
  (SELECT count(*) FROM (SELECT * EXCEPT (key_copies) FROM healthcare_dev.gold.readmission_events
                         EXCEPT ALL
                         SELECT * FROM healthcare_dev.ops.pyspark_readmission_events)) AS events_only_in_gold,
  (SELECT count(*) FROM (SELECT * FROM healthcare_dev.ops.pyspark_readmission_events
                         EXCEPT ALL
                         SELECT * EXCEPT (key_copies) FROM healthcare_dev.gold.readmission_events)) AS events_only_in_pyspark;

-- readmission_signals, the model's table, must not have moved at all.
-- ops.signals_before was dropped once this read 0 (archive/sql/phase7_cleanup.sql),
-- so this second query is a record of phase 7 and fails if rerun.
SELECT
  (SELECT count(*) FROM (SELECT * EXCEPT (key_copies) FROM healthcare_dev.gold.readmission_signals
                         EXCEPT ALL
                         SELECT * FROM healthcare_dev.ops.signals_before)) AS signals_only_now,
  (SELECT count(*) FROM (SELECT * FROM healthcare_dev.ops.signals_before
                         EXCEPT ALL
                         SELECT * EXCEPT (key_copies) FROM healthcare_dev.gold.readmission_signals)) AS signals_only_before;
