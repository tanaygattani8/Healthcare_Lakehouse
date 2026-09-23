CREATE TABLE IF NOT EXISTS healthcare_dev.ops.phi_clearance
  (user_email STRING, level STRING)
  COMMENT 'Who may read PHI unmasked. UC groups are the production upgrade path.';

CREATE OR REPLACE FUNCTION healthcare_dev.ops.is_cleared()
RETURN EXISTS (SELECT 1 FROM healthcare_dev.ops.phi_clearance
                WHERE user_email = current_user() AND level = 'full');

CREATE OR REPLACE FUNCTION healthcare_dev.ops.mask_text(v STRING)
RETURN CASE WHEN healthcare_dev.ops.is_cleared() THEN v ELSE '***' END;

CREATE OR REPLACE FUNCTION healthcare_dev.ops.mask_date(d DATE)
RETURN CASE WHEN healthcare_dev.ops.is_cleared() THEN d ELSE make_date(year(d), 1, 1) END;

CREATE OR REPLACE FUNCTION healthcare_dev.ops.mask_point(v DOUBLE)
RETURN CASE WHEN healthcare_dev.ops.is_cleared() THEN v ELSE NULL END;

CREATE OR REPLACE FUNCTION healthcare_dev.ops.mask_zip(v STRING)
RETURN CASE WHEN healthcare_dev.ops.is_cleared() THEN v ELSE substr(v, 1, 3) END;
