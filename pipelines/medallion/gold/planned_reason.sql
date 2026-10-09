-- Admit reasons meaning a scheduled stay (D57); cancer is in planned_procedure instead (D64).

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.planned_reason
COMMENT "Admission reasons treated as planned. A planned readmission does not count."
TBLPROPERTIES ("quality" = "gold")
AS SELECT * FROM VALUES
    ('Sterilization requested (situation)'),
    ('Awaiting transplantation of kidney (situation)'),
    ('Sleep disorder (disorder)')
AS t(reason_description);
