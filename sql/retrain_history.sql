-- Phase 9's decision record: rates and verdicts only.
SELECT as_of, mode, champion_version, check_stays, target,
       champion_rate, champion_low, champion_high, triggered,
       cutoff_rate, cutoff_workload, retrain_rate, retrain_workload, retrain_ranking,
       outcome, new_version, alias, shifted_features
FROM healthcare_dev.ml.retrain_history
ORDER BY written_at;
