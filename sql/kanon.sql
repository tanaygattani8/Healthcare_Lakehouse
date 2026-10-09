-- Phase 3b step 7: k = people sharing birth, death and gender; full spread for plan, safe and released (D56).

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

-- Must be 0: nobody released shares their combination with fewer than 4 others.
SELECT coalesce(sum(people), 0) AS released_people_below_k5_must_be_0
FROM healthcare_dev.ops.kanon_spread
WHERE version = 'released' AND k NOT IN ('5-10', '11+');

SELECT sum(CASE WHEN years_suppressed THEN 1 ELSE 0 END) AS people_with_years_blanked,
       count(*) AS patients
FROM healthcare_dev.deid.patient;
