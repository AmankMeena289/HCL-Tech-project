-- Stretch KPI 5: Average inpatient length of stay by hospital
-- Eligible Inpatient encounters only. Length of stay = discharge - admit, in days.
SELECT
    h.hospital_id,
    h.hospital_name,
    COUNT(*)                                                               AS inpatient_encounters,
    CAST(ROUND(AVG(e.length_of_stay_hours) / 24, 2) AS DECIMAL(10, 2))     AS avg_length_of_stay_days,
    CAST(ROUND(MAX(e.length_of_stay_hours) / 24, 2) AS DECIMAL(10, 2))     AS max_length_of_stay_days
FROM fct_encounter e
JOIN dim_hospital h ON h.hospital_id = e.hospital_id
WHERE e.is_eligible AND e.encounter_type = 'Inpatient'
GROUP BY h.hospital_id, h.hospital_name
ORDER BY h.hospital_id
