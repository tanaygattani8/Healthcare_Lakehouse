CREATE CATALOG IF NOT EXISTS healthcare_dev;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.bronze;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.silver;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.gold;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.deid;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.ops;
CREATE VOLUME IF NOT EXISTS healthcare_dev.bronze.landing;

CREATE CATALOG IF NOT EXISTS healthcare;
CREATE SCHEMA IF NOT EXISTS healthcare.bronze;
CREATE SCHEMA IF NOT EXISTS healthcare.silver;
CREATE SCHEMA IF NOT EXISTS healthcare.gold;
CREATE SCHEMA IF NOT EXISTS healthcare.deid;
CREATE SCHEMA IF NOT EXISTS healthcare.ops;
CREATE VOLUME IF NOT EXISTS healthcare.bronze.landing;