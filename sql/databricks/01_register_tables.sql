-- Optional: register the gold, quarantine and audit Delta folders as tables so
-- analysts can query them in Databricks SQL. Replace <storage-account>.
-- (Registering tables is an optional extension; the pipeline works without it.)

CREATE SCHEMA IF NOT EXISTS carevista_gold;
CREATE SCHEMA IF NOT EXISTS carevista_ops;

CREATE TABLE IF NOT EXISTS carevista_gold.dim_patient      USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/dim_patient';
CREATE TABLE IF NOT EXISTS carevista_gold.dim_service      USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/dim_service';
CREATE TABLE IF NOT EXISTS carevista_gold.dim_hospital     USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/dim_hospital';
CREATE TABLE IF NOT EXISTS carevista_gold.fct_encounter    USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/fct_encounter';
CREATE TABLE IF NOT EXISTS carevista_gold.fct_billing_line USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/fct_billing_line';

CREATE TABLE IF NOT EXISTS carevista_gold.kpi1_revenue_by_department_month USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/kpi1_revenue_by_department_month';
CREATE TABLE IF NOT EXISTS carevista_gold.kpi2_hospital_encounter_type     USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/kpi2_hospital_encounter_type';
CREATE TABLE IF NOT EXISTS carevista_gold.kpi3_top10_patients              USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/kpi3_top10_patients';
CREATE TABLE IF NOT EXISTS carevista_gold.kpi4_patient_category_profile    USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/kpi4_patient_category_profile';
CREATE TABLE IF NOT EXISTS carevista_gold.kpi5_inpatient_length_of_stay    USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/kpi5_inpatient_length_of_stay';
CREATE TABLE IF NOT EXISTS carevista_gold.kpi6_region_service_category_mix USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/gold/kpi6_region_service_category_mix';

CREATE TABLE IF NOT EXISTS carevista_ops.pipeline_audit USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/audit/pipeline_audit';
CREATE TABLE IF NOT EXISTS carevista_ops.run_history    USING DELTA LOCATION 'abfss://lake@<storage-account>.dfs.core.windows.net/carevista/audit/run_history';
