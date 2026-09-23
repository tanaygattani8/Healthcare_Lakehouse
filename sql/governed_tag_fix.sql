-- Phase 3a, Task 1 step 1 — the phi_category vocabulary.
--
-- SET VALUES is declarative: this list replaces whatever is registered. Safe
-- while no column carries the tag. After tagging, dropping a value here
-- orphans every column that used it.
--
-- Three corrections to the list the ABAC probe registered:
--
--   * DRIVERS is a licence number and PASSPORT is "any other unique
--     identifying number". Neither is an SSN, so 'license' and 'other_id'
--     exist rather than forcing both under 'ssn'.
--   * ZIP truncates to three digits while ADDRESS and CITY redact outright.
--     One policy names one mask function, so those cannot share a value.
--   * latitude and longitude are DOUBLE. A mask returns the column's own
--     type, so they cannot go through the STRING mask the other geography
--     columns use. Hence 'geo_point'.
--
-- 'contact' is gone. Synthea's patients.csv has no phone or email column.

ALTER GOVERNED TAG phi_category
  SET VALUES ('name', 'date', 'geography', 'zip', 'geo_point',
              'ssn', 'license', 'other_id');

SHOW GOVERNED TAGS LIKE 'phi*';
