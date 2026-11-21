-- Stretch KPI 6: Revenue mix by hospital region and service category
-- share_of_region_pct = this category's revenue / the region's total revenue x 100.
WITH revenue AS (
    SELECT
        h.hospital_region,
        s.service_category,
        SUM(b.line_charge) AS billed_revenue
    FROM fct_billing_line b
    JOIN fct_encounter e ON e.encounter_id = b.encounter_id AND e.is_eligible
    JOIN dim_hospital h  ON h.hospital_id  = e.hospital_id
    JOIN dim_service s   ON s.service_id   = b.service_id
    GROUP BY h.hospital_region, s.service_category
)
SELECT
    hospital_region,
    service_category,
    CAST(billed_revenue AS DECIMAL(18, 2)) AS billed_revenue,
    CAST(ROUND(billed_revenue * 100 / SUM(billed_revenue) OVER (PARTITION BY hospital_region), 2) AS DECIMAL(6, 2))
        AS share_of_region_pct
FROM revenue
ORDER BY hospital_region, billed_revenue DESC, service_category
