CREATE CATALOG IF NOT EXISTS healthcare_dev;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.bronze;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.silver;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.gold;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.deid;
CREATE SCHEMA IF NOT EXISTS healthcare_dev.ops;
CREATE VOLUME IF NOT EXISTS healthcare_dev.bronze.landing;
