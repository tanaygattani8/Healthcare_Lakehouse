-- Phase 3a, Task 1 step 5 — demonstrate the masks opening and closing.
--
-- Separate from governance_policies.sql because this mutates the clearance
-- table and is meant to be re-run on demand. It leaves clearance restored.
--
-- Expected, in order:
--   1. real values
--   2. '***' for name and identifiers, three-digit ZIP, 1971-01-01, NULL coords
--   3. real values again
--
-- If step 2 shows real values, the policies are not matching — check that the
-- tags are still present with governance_check.sql before suspecting the
-- policies themselves.

SELECT 'cleared' AS state, SSN, FIRST, CITY, ZIP, birth_date, latitude
FROM healthcare_dev.silver.patient
WHERE patient_id = (SELECT min(patient_id) FROM healthcare_dev.silver.patient);

DELETE FROM healthcare_dev.ops.phi_clearance WHERE user_email = current_user();

SELECT 'revoked' AS state, SSN, FIRST, CITY, ZIP, birth_date, latitude
FROM healthcare_dev.silver.patient
WHERE patient_id = (SELECT min(patient_id) FROM healthcare_dev.silver.patient);

INSERT INTO healthcare_dev.ops.phi_clearance VALUES (current_user(), 'full');

SELECT 'restored' AS state, SSN, FIRST, CITY, ZIP, birth_date, latitude
FROM healthcare_dev.silver.patient
WHERE patient_id = (SELECT min(patient_id) FROM healthcare_dev.silver.patient);
