-- KPI 3: Top ten patients by billed amount
-- Highest billed first; ties broken by patient_id ascending.
-- Only patient_id is shown (no names, emails or phone numbers).
WITH encounter_bill AS (
    SELECT
        e.encounter_id,
        e.patient_id,
        COALESCE(SUM(b.line_charge), CAST(0 AS DECIMAL(18, 2))) AS bill
    FROM fct_encounter e
    LEFT JOIN fct_billing_line b ON b.encounter_id = e.encounter_id
    WHERE e.is_eligible
    GROUP BY e.encounter_id, e.patient_id
),
patient_bill AS (
    SELECT
        p.patient_id,
        COUNT(eb.encounter_id)                 AS eligible_encounters,
        CAST(SUM(eb.bill) AS DECIMAL(18, 2))   AS billed_amount
    FROM encounter_bill eb
    JOIN dim_patient p ON p.patient_id = eb.patient_id
    GROUP BY p.patient_id
),
ranked AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY billed_amount DESC, patient_id ASC) AS rank,
        patient_id,
        eligible_encounters,
        billed_amount
    FROM patient_bill
)
SELECT rank, patient_id, eligible_encounters, billed_amount
FROM ranked
WHERE rank <= 10
ORDER BY rank
