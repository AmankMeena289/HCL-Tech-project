-- Evidence queries to run in Databricks SQL after a pipeline run.

-- 1. Rows read / accepted / rejected per file for a batch
SELECT step, source_file, rows_read, rows_accepted, rows_rejected, detail
FROM carevista_ops.pipeline_audit
WHERE batch_id = 'B20260630' AND step IN ('bronze', 'silver')
ORDER BY step DESC, source_file;

-- 2. Every attempt of every task (shows retries)
SELECT run_id, task, attempt, status, started_at, finished_at, message
FROM carevista_ops.run_history
WHERE batch_id = 'B20260630'
ORDER BY started_at;

-- 3. Idempotency check: run after a rerun. Each count must be the same as before.
SELECT 'fct_billing_line' AS t, COUNT(*) AS n FROM carevista_gold.fct_billing_line
UNION ALL SELECT 'fct_encounter', COUNT(*) FROM carevista_gold.fct_encounter
UNION ALL SELECT 'dim_patient',   COUNT(*) FROM carevista_gold.dim_patient;

-- 4. Revenue reconciles across KPIs (all three numbers must match)
SELECT
  (SELECT SUM(billed_revenue) FROM carevista_gold.kpi1_revenue_by_department_month) AS kpi1_total,
  (SELECT SUM(billed_amount)  FROM carevista_gold.kpi2_hospital_encounter_type)     AS kpi2_total,
  (SELECT SUM(billed_amount)  FROM carevista_gold.kpi4_patient_category_profile)    AS kpi4_total;
