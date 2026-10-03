-- Procedures that make a hospital stay planned whatever its admit reason
-- (decision.md D64). CMS treats maintenance chemotherapy as always planned,
-- and its readmission measures leave stays for cancer treatment out of the
-- index stays too. Synthea's lung cancer module schedules a chemo and
-- radiation stay about every 25 days; counted as unplanned, those cycles
-- were 184 of the 201 readmissions.
--
-- kind says what a code does (D68):
--   cancer_treatment: the stay is planned AND cannot start a window (D64).
--   heart_surgery: a return for a scheduled CABG or aortic valve operation
--     is planned (CMS treats both as potentially planned), but the surgery
--     stay can still start a window: CABG patients are readmitted from it.
--   emergency_heart_surgery: overrides heart_surgery. An emergency operation
--     is an acute return, so it counts.

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
