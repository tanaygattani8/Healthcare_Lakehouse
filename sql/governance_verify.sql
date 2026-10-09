-- Phase 3a: masks open, close, open again (real, then '***'/3-digit ZIP/1971-01-01/NULL, then real).

SELECT 'cleared' AS state, SSN, FIRST, CITY, ZIP, birth_date, latitude
FROM healthcare_dev.silver.patient
WHERE patient_id = (SELECT min(patient_id) FROM healthcare_dev.silver.patient);

DELETE FROM healthcare_dev.ops.phi_clearance WHERE user_email = current_user();

SELECT 'revoked' AS state, SSN, FIRST, CITY, ZIP, birth_date, latitude
FROM healthcare_dev.silver.patient
WHERE patient_id = (SELECT min(patient_id) FROM healthcare_dev.silver.patient);

-- Three columns since scope_state; the two-value insert left the user uncleared (D79).
INSERT INTO healthcare_dev.ops.phi_clearance (user_email, level, scope_state)
VALUES (current_user(), 'full', '*');

SELECT 'restored' AS state, SSN, FIRST, CITY, ZIP, birth_date, latitude
FROM healthcare_dev.silver.patient
WHERE patient_id = (SELECT min(patient_id) FROM healthcare_dev.silver.patient);
