-- KPI 2: Encounters and average bill by hospital and encounter type
-- An eligible encounter with no billing lines counts as a bill of 0.
-- average_bill = billed_amount / eligible_encounters, rounded to 2 decimals half up.
WITH encounter_bill AS (
    SELECT
        e.encounter_id,
        e.hospital_id,
        e.encounter_type,
        COALESCE(SUM(b.line_charge), CAST(0 AS DECIMAL(18, 2))) AS bill
    FROM fct_encounter e
    LEFT JOIN fct_billing_line b ON b.encounter_id = e.encounter_id
    WHERE e.is_eligible
    GROUP BY e.encounter_id, e.hospital_id, e.encounter_type
)
SELECT
    h.hospital_id,
    eb.encounter_type,
    COUNT(*)                                                   AS eligible_encounters,
    CAST(SUM(eb.bill) AS DECIMAL(18, 2))                       AS billed_amount,
    CAST(ROUND(SUM(eb.bill) / COUNT(*), 2) AS DECIMAL(18, 2))  AS average_bill
FROM encounter_bill eb
JOIN dim_hospital h ON h.hospital_id = eb.hospital_id
GROUP BY h.hospital_id, eb.encounter_type
ORDER BY h.hospital_id, eb.encounter_type
