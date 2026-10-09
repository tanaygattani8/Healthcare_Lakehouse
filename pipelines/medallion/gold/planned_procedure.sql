-- Procedures that make a stay planned whatever its reason (D64, D68).
-- cancer_treatment: planned and can't start a window; heart_surgery: a planned return; emergency_heart_surgery overrides it.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.planned_procedure
COMMENT "Procedures that make a stay planned: cancer treatment (D64) and scheduled heart surgery (D68). The one place these codes are defined."
TBLPROPERTIES ("quality" = "gold")
AS SELECT * FROM VALUES
    ('703423002', 'Combined chemotherapy and radiation therapy (procedure)', 'cancer_treatment'),
    ('367336001', 'Chemotherapy (procedure)', 'cancer_treatment'),
    ('232717009', 'Coronary artery bypass grafting (procedure)', 'heart_surgery'),
    ('418824004', 'Off-pump coronary artery bypass (procedure)', 'heart_surgery'),
    ('26212005', 'Replacement of aortic valve (procedure)', 'heart_surgery'),
    ('1155885007', 'Repair of aortic valve (procedure)', 'heart_surgery'),
    ('773996000', 'Transcatheter aortic valve implantation (procedure)', 'heart_surgery'),
    ('414088005', 'Emergency coronary artery bypass graft (procedure)', 'emergency_heart_surgery')
AS t(code, display, kind);
