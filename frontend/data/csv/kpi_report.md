# CareVista KPI report - batch B20260630 (cutoff 2026-06-30 23:59:59)

All amounts are INR, excluding tax. Only eligible encounters (rule E4) are counted.

## Audit - rows read, accepted and rejected per file

| step | source_file | rows_read | rows_accepted | rows_rejected | detail |
|---|---|---|---|---|---|
| silver | encounter_services.csv | 572 | 531 | 41 | L4_ENCOUNTER_REJECTED=16; EXACT_DUPLICATE=8; L2_NON_POSITIVE_QUANTITY=4; L4_UNKNOWN_ENCOUNTER=4; L2_DISCOUNT_OUT_OF_RANGE=3; L2_NEGATIVE_UNIT_PRICE=3; L4_UNKNOWN_SERVICE=3 |
| silver | encounters.csv | 208 | 194 | 14 | EXACT_DUPLICATE=6; E3_UNKNOWN_PATIENT=5; E3_DISCHARGE_BEFORE_ADMIT=3 |
| silver | patients.csv | 113 | 100 | 13 | SUPERSEDED_VERSION=6; EXACT_DUPLICATE=5; P1_BLANK_PATIENT_ID=2 |
| silver | services.csv | 22 | 20 | 2 | EXACT_DUPLICATE=2 |
| bronze | encounter_services.csv | 572 | 572 | 0 | null |
| bronze | encounters.csv | 208 | 208 | 0 | null |
| bronze | patients.csv | 113 | 113 | 0 | null |
| bronze | services.csv | 22 | 22 | 0 | null |

## KPI 1 - Billed revenue by department per month (INR)

| month | department | billed_revenue |
|---|---|---|
| 2026-01 | Consultation | 32358.45 |
| 2026-01 | Laboratory | 27213.40 |
| 2026-01 | Pharmacy | 14502.90 |
| 2026-01 | Procedures | 246937.65 |
| 2026-01 | Radiology | 5886.70 |
| 2026-01 | Room & Nursing | 291522.90 |
| 2026-02 | Consultation | 26125.35 |
| 2026-02 | Laboratory | 17881.30 |
| 2026-02 | Pharmacy | 9301.90 |
| 2026-02 | Procedures | 46149.90 |
| 2026-02 | Radiology | 10809.55 |
| 2026-02 | Room & Nursing | 170787.50 |
| 2026-03 | Consultation | 29469.40 |
| 2026-03 | Laboratory | 20033.95 |
| 2026-03 | Pharmacy | 17875.55 |
| 2026-03 | Procedures | 112062.05 |
| 2026-03 | Radiology | 10094.20 |
| 2026-03 | Room & Nursing | 305135.50 |
| 2026-04 | Consultation | 26219.90 |
| 2026-04 | Laboratory | 27002.15 |
| 2026-04 | Pharmacy | 24865.85 |
| 2026-04 | Procedures | 105781.00 |
| 2026-04 | Radiology | 14172.95 |
| 2026-04 | Room & Nursing | 392253.30 |
| 2026-05 | Consultation | 25606.75 |
| 2026-05 | Laboratory | 19725.70 |
| 2026-05 | Pharmacy | 23917.20 |
| 2026-05 | Procedures | 158673.05 |
| 2026-05 | Radiology | 11171.05 |
| 2026-05 | Room & Nursing | 199823.65 |
| 2026-06 | Consultation | 25564.60 |
| 2026-06 | Laboratory | 10405.70 |
| 2026-06 | Pharmacy | 7108.15 |
| 2026-06 | Procedures | 3957.30 |
| 2026-06 | Radiology | 15972.40 |
| 2026-06 | Room & Nursing | 51334.60 |

## KPI 2 - Encounters and average bill by hospital and encounter type (INR)

| hospital_id | encounter_type | eligible_encounters | billed_amount | average_bill |
|---|---|---|---|---|
| H01 | Emergency | 4 | 11463.20 | 2865.80 |
| H01 | Inpatient | 14 | 709115.90 | 50651.14 |
| H01 | Outpatient | 9 | 17277.25 | 1919.69 |
| H02 | Emergency | 7 | 18171.05 | 2595.86 |
| H02 | Inpatient | 11 | 473833.95 | 43075.81 |
| H02 | Outpatient | 22 | 53301.35 | 2422.79 |
| H03 | Emergency | 8 | 15650.40 | 1956.30 |
| H03 | Inpatient | 9 | 338068.70 | 37563.19 |
| H03 | Outpatient | 12 | 19936.95 | 1661.41 |
| H04 | Emergency | 7 | 19744.25 | 2820.61 |
| H04 | Inpatient | 6 | 239505.45 | 39917.58 |
| H04 | Outpatient | 6 | 13859.15 | 2309.86 |
| H05 | Emergency | 6 | 16137.70 | 2689.62 |
| H05 | Inpatient | 9 | 281910.80 | 31323.42 |
| H05 | Outpatient | 9 | 26904.20 | 2989.36 |
| H06 | Emergency | 3 | 5527.10 | 1842.37 |
| H06 | Inpatient | 8 | 238122.10 | 29765.26 |
| H06 | Outpatient | 18 | 39173.95 | 2176.33 |

## KPI 3 - Top ten patients by billed amount (INR)

| rank | patient_id | eligible_encounters | billed_amount |
|---|---|---|---|
| 1 | PT087 | 4 | 185207.50 |
| 2 | PT091 | 5 | 164918.75 |
| 3 | PT088 | 6 | 132141.40 |
| 4 | PT018 | 5 | 115978.00 |
| 5 | PT007 | 5 | 109230.30 |
| 6 | PT095 | 7 | 108977.25 |
| 7 | PT092 | 2 | 96121.15 |
| 8 | PT030 | 3 | 84567.05 |
| 9 | PT024 | 7 | 82169.45 |
| 10 | PT056 | 1 | 82005.35 |

## KPI 4 - Patient category profile (INR)

| patient_category | patients | patients_with_eligible_encounters | eligible_encounters | billed_amount | average_bill |
|---|---|---|---|---|---|
| SelfPay | 35 | 23 | 46 | 735921.85 | 15998.30 |
| Insured | 44 | 31 | 87 | 1327835.80 | 15262.48 |
| Corporate | 21 | 12 | 35 | 473945.80 | 13541.31 |

## Stretch KPI 5 - Average inpatient length of stay by hospital (days)

| hospital_id | hospital_name | inpatient_encounters | avg_length_of_stay_days | max_length_of_stay_days |
|---|---|---|---|---|
| H01 | CareVista Delhi Central | 14 | 5.04 | 8.21 |
| H02 | CareVista Chandigarh | 11 | 4.61 | 8.03 |
| H03 | CareVista Bengaluru | 9 | 4.21 | 8.04 |
| H04 | CareVista Chennai | 6 | 4.70 | 7.90 |
| H05 | CareVista Mumbai | 9 | 5.11 | 8.24 |
| H06 | CareVista Pune | 8 | 4.50 | 7.96 |

## Stretch KPI 6 - Revenue mix by region and service category (INR)

| hospital_region | service_category | billed_revenue | share_of_region_pct |
|---|---|---|---|
| North | Accommodation | 695780.65 | 54.22 |
| North | Procedure | 401628.65 | 31.30 |
| North | Diagnostic | 77888.95 | 6.07 |
| North | Consultation | 66462.20 | 5.18 |
| North | Medication | 41402.25 | 3.23 |
| South | Accommodation | 377557.20 | 58.38 |
| South | Procedure | 153040.25 | 23.66 |
| South | Diagnostic | 48111.50 | 7.44 |
| South | Consultation | 45390.10 | 7.02 |
| South | Medication | 22665.85 | 3.50 |
| West | Accommodation | 337519.60 | 55.53 |
| West | Procedure | 118892.05 | 19.56 |
| West | Diagnostic | 64368.60 | 10.59 |
| West | Consultation | 53492.15 | 8.80 |
| West | Medication | 33503.45 | 5.51 |

## Workflow run history (every attempt)

| run_id | task | attempt | status | started_at | finished_at | message |
|---|---|---|---|---|---|---|
| run-20261121T153055-B20260630 | landing | 1 | Succeeded | 2026-11-21 10:02:10.037832 | 2026-11-21 10:03:02.707027 | null |
| run-20261121T153055-B20260630 | bronze | 1 | Succeeded | 2026-11-21 10:05:24.416717 | 2026-11-21 10:06:09.328868 | null |
| run-20261121T153055-B20260630 | silver | 1 | Succeeded | 2026-11-21 10:08:25.260755 | 2026-11-21 10:10:06.395545 | null |
| run-20261121T153713-B20260630 | landing | 1 | Succeeded | 2026-11-21 10:08:37.641820 | 2026-11-21 10:09:16.835192 | null |
| run-20261121T153055-B20260630 | gold | 1 | Succeeded | 2026-11-21 10:12:31.238379 | 2026-11-21 10:14:08.511001 | null |
