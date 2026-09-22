-- No IF EXISTS on DROP POLICY: the parser reads `IF` as the policy name and
-- then demands ON. So this statement fails if the policy is already gone.
DROP POLICY probe_mask_all ON SCHEMA healthcare_dev.ops;
DROP TABLE IF EXISTS healthcare_dev.ops.probe_abac;
DROP FUNCTION IF EXISTS healthcare_dev.ops.probe_redact;
-- Deliberately NOT dropped: the governed tag is account-level, Task 1 needs
-- this exact key, and re-registering it is pure churn. Its value list can be
-- changed in place with ALTER GOVERNED TAG. To reset the account fully:
--   DROP GOVERNED TAG IF EXISTS phi_category;
