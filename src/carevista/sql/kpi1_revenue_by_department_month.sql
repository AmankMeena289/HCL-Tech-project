-- KPI 1: Billed revenue by department per month
-- Sum of line_charge (rule L3) for lines of eligible encounters (rule E4),
-- grouped by billing department and the month of service_date.
SELECT
    b.service_month                              AS month,
    s.department                                 AS department,
    CAST(SUM(b.line_charge) AS DECIMAL(18, 2))   AS billed_revenue
FROM fct_billing_line b
JOIN fct_encounter e ON e.encounter_id = b.encounter_id AND e.is_eligible
JOIN dim_service s   ON s.service_id   = b.service_id
GROUP BY b.service_month, s.department
ORDER BY month, department
