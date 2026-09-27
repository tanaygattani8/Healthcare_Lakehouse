-- Reference tables. Built from bronze because silver never modelled them:
-- nothing upstream needed providers until gold asked "who saw them".

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.dim_date
COMMENT "One row per calendar day the encounters span. date_key is yyyymmdd."
TBLPROPERTIES ("quality" = "gold")
AS
WITH bounds AS (
    SELECT to_date(min(started_at)) AS first_day,
           to_date(max(coalesce(stopped_at, started_at))) AS last_day
    FROM ${catalog}.silver.encounter
)
SELECT cast(date_format(d, 'yyyyMMdd') AS INT) AS date_key,
       d                                     AS calendar_date,
       year(d)                               AS year,
       quarter(d)                            AS quarter,
       month(d)                              AS month,
       dayofweek(d)                          AS day_of_week,
       dayofweek(d) IN (1, 7)                AS is_weekend
FROM bounds
LATERAL VIEW explode(sequence(first_day, last_day, INTERVAL 1 DAY)) t AS d;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.dim_organization
COMMENT "Hospitals and clinics."
TBLPROPERTIES ("quality" = "gold")
AS SELECT Id AS organization_id, NAME AS name, CITY AS city, STATE AS state
   FROM ${catalog}.bronze.br_organizations;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.dim_provider
COMMENT "Clinicians. Synthetic names; clinicians are not patients."
TBLPROPERTIES ("quality" = "gold")
AS SELECT Id AS provider_id, ORGANIZATION AS organization_id,
          NAME AS name, GENDER AS gender, SPECIALITY AS speciality
   FROM ${catalog}.bronze.br_providers;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.dim_payer
COMMENT "Insurers."
TBLPROPERTIES ("quality" = "gold")
AS SELECT Id AS payer_id, NAME AS name, OWNERSHIP AS ownership
   FROM ${catalog}.bronze.br_payers;
