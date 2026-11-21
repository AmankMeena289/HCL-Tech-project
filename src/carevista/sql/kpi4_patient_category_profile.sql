-- KPI 4: Patient category profile (uses each patient's CURRENT category, rule P3)
-- patients                          = all current patients in the category
-- patients_with_eligible_encounters = of those, how many had an eligible encounter
-- average_bill is NULL (not 0) when a category has no eligible encounters.
WITH categories AS (
    SELECT * FROM VALUES ('SelfPay', 1), ('Insured', 2), ('Corporate', 3) AS t(patient_category, sort_order)
),
encounter_bill AS (
    SELECT
        e.encounter_id,
        e.patient_id,
        COALESCE(SUM(b.line_charge), CAST(0 AS DECIMAL(18, 2))) AS bill
    FROM fct_encounter e
    LEFT JOIN fct_billing_line b ON b.encounter_id = e.encounter_id
    WHERE e.is_eligible
    GROUP BY e.encounter_id, e.patient_id
),
patient_counts AS (
    SELECT patient_category, COUNT(*) AS patients
    FROM dim_patient
    GROUP BY patient_category
),
billing AS (
    SELECT
        p.patient_category,
        COUNT(DISTINCT p.patient_id) AS patients_with_eligible_encounters,
        COUNT(eb.encounter_id)       AS eligible_encounters,
        SUM(eb.bill)                 AS billed_amount
    FROM encounter_bill eb
    JOIN dim_patient p ON p.patient_id = eb.patient_id
    GROUP BY p.patient_category
)
SELECT
    c.patient_category,
    COALESCE(pc.patients, 0)                                           AS patients,
    COALESCE(b.patients_with_eligible_encounters, 0)                   AS patients_with_eligible_encounters,
    COALESCE(b.eligible_encounters, 0)                                 AS eligible_encounters,
    CAST(COALESCE(b.billed_amount, 0) AS DECIMAL(18, 2))               AS billed_amount,
    CASE
        WHEN COALESCE(b.eligible_encounters, 0) = 0 THEN CAST(NULL AS DECIMAL(18, 2))
        ELSE CAST(ROUND(b.billed_amount / b.eligible_encounters, 2) AS DECIMAL(18, 2))
    END                                                                AS average_bill
FROM categories c
LEFT JOIN patient_counts pc ON pc.patient_category = c.patient_category
LEFT JOIN billing b         ON b.patient_category  = c.patient_category
ORDER BY c.sort_order
