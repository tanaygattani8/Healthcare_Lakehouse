-- Phase 3b step 7 — could anyone still be picked out of deid.patient?
--
-- k = how many people share a combination of the columns an outsider could
-- know: birth, death and gender. k = 1 is one person, alone and findable.
-- The whole spread is reported, not the minimum: "minimum k is 1" hides
-- whether that is one person or four hundred.
--
-- Three versions, so the cost of each choice is visible (decision.md D56):
--   plan      full birth date + 3-digit ZIP + gender, as first planned
--   safe      what HIPAA Safe Harbor allows: birth year + 3-digit ZIP + gender
--   released  what deid.patient holds: 5-year bands, no ZIP, k < 5 blanked
-- Saved to ops.kanon_spread for the app. Counts only.

CREATE OR REPLACE TABLE healthcare_dev.ops.kanon_spread
COMMENT "Phase 3b step 7: how many people share each quasi-identifier combination, for three levels of detail. Counts only."
AS
WITH plan AS (
    SELECT count(*) AS k FROM healthcare_dev.silver.patient
    GROUP BY birth_date, substring(ZIP, 1, 3), GENDER
),
safe AS (
    SELECT count(*) AS k FROM healthcare_dev.silver.patient
    GROUP BY year(birth_date), substring(ZIP, 1, 3), GENDER
),
released AS (
    SELECT count(*) AS k FROM healthcare_dev.deid.patient
    GROUP BY birth_year_from, gender, death_year_from
),
spread AS (
    SELECT 'plan' AS version, k FROM plan
    UNION ALL SELECT 'safe', k FROM safe
    UNION ALL SELECT 'released', k FROM released
)
SELECT version,
       CASE WHEN k >= 11 THEN '11+' WHEN k >= 5 THEN '5-10' ELSE cast(k AS STRING) END AS k,
       count(*) AS groups, sum(k) AS people
FROM spread
GROUP BY 1, 2;

SELECT version, k, groups, people FROM healthcare_dev.ops.kanon_spread
ORDER BY version, CASE k WHEN '11+' THEN 99 WHEN '5-10' THEN 5 ELSE cast(k AS INT) END;

-- Must be 0: nobody in the released table shares their combination with
-- fewer than 4 others.
SELECT coalesce(sum(people), 0) AS released_people_below_k5_must_be_0
FROM healthcare_dev.ops.kanon_spread
WHERE version = 'released' AND k NOT IN ('5-10', '11+');

SELECT sum(CASE WHEN years_suppressed THEN 1 ELSE 0 END) AS people_with_years_blanked,
       count(*) AS patients
FROM healthcare_dev.deid.patient;
