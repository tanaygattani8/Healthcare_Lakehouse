-- Phase 3a: the phi_category vocabulary; SET VALUES replaces the list, so never drop a value in use.

ALTER GOVERNED TAG phi_category
  SET VALUES ('name', 'date', 'geography', 'zip', 'geo_point',
              'ssn', 'license', 'other_id');

SHOW GOVERNED TAGS LIKE 'phi*';
