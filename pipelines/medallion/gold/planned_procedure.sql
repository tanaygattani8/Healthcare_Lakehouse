-- Procedures that make a hospital stay planned whatever its admit reason
-- (decision.md D64). CMS treats maintenance chemotherapy as always planned,
-- and its readmission measures leave stays for cancer treatment out of the
-- index stays too. Synthea's lung cancer module schedules a chemo and
-- radiation stay about every 25 days; counted as unplanned, those cycles
-- were 184 of the 201 readmissions.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.planned_procedure
COMMENT "Procedures that make a stay planned (cancer treatment). The one place these codes are defined."
TBLPROPERTIES ("quality" = "gold")
AS SELECT * FROM VALUES
    ('703423002', 'Combined chemotherapy and radiation therapy (procedure)'),
    ('367336001', 'Chemotherapy (procedure)')
AS t(code, display);
