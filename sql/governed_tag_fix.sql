-- Corrects the value list the ABAC probe left behind.
--
-- The probe registered ('name','ssn','date','geography','contact'). That list
-- cannot describe silver.patient: DRIVERS is a licence number and PASSPORT is
-- "any other unique identifying number", neither of which is an SSN, and
-- nothing in Synthea's patients.csv is a phone or email, so 'contact' is dead.
--
-- Six values, four mask functions — 'license' and 'other_id' both take mask_id.
-- SET VALUES is declarative: it replaces the list outright. Safe to run now
-- because no column carries this tag yet; after tagging it would orphan them.

ALTER GOVERNED TAG phi_category
  SET VALUES ('name', 'date', 'geography', 'ssn', 'license', 'other_id');

SHOW GOVERNED TAGS LIKE 'phi*';
