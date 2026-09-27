-- Admission reasons that mean a scheduled stay, not a relapse (probe P3,
-- decision.md D57). A readmission for one of these does not count.
-- Cancer stays are NOT here: the reason cannot tell a chemotherapy stay
-- (planned) from a complication (unplanned), so they count as unplanned.
-- Sleep disorder is assumed to be an overnight sleep study.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.planned_reason
COMMENT "Admission reasons treated as planned. A planned readmission does not count."
TBLPROPERTIES ("quality" = "gold")
AS SELECT * FROM VALUES
    ('Sterilization requested (situation)'),
    ('Awaiting transplantation of kidney (situation)'),
    ('Sleep disorder (disorder)')
AS t(reason_description);
