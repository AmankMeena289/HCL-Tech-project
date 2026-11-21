# Cleansing rules

The use-case document mentions "rule E4" (eligible encounters) and "rule L3" (line charge) but does not list the rules. The data pack files it mentions (Data_Dictionary.csv, README) were not supplied. So we wrote the full rule set below, and gave rule IDs that match how the document uses E4 and L3.

**How a rule works:** every row is checked against every rule for its file.
- A row that passes all checks goes to **silver**.
- A row that fails any check goes to **quarantine**, unchanged, with every failed rule listed in `reject_reason` (for example `L2_NON_POSITIVE_QUANTITY; L4_UNKNOWN_SERVICE`).
- The **audit** table checks that rows read = rows accepted + rows rejected for every file.

Every quarantined row keeps `batch_id`, `source_file` and `source_row_num`, so you can find the exact line in the original file.

The "Rows hit" column shows how many rows each rule caught in the supplied data (batch B20260630).

## General rules (all files)

| Rule | What it does | Rows hit |
|---|---|---|
| G1 | Bronze stops the run if a file's header is not the expected column list (protects against a changed file layout). | 0 |
| G2 | A line that cannot be split into the expected number of columns is rejected as `MALFORMED_ROW`. | 0 |
| G3 | Leading and trailing spaces are trimmed from all text. An empty value is treated as missing (NULL). | 9 first names had leading spaces |
| G4 | Dates can be `YYYY-MM-DD` or `DD/MM/YYYY`. Timestamps can be `YYYY-MM-DD HH:mm[:ss]` or `DD/MM/YYYY HH:mm[:ss]`. `DD/MM` is always read day first. Impossible dates (such as 31/02/2026) become invalid. | 30 registration dates, 43 admit and 37 discharge timestamps, 141 service dates were `DD/MM/YYYY` |
| G5 | Timestamps are stored as "timestamp without time zone", so 10:49 stays 10:49. The data is already Asia/Kolkata local time, so no conversion is done. | all timestamps |
| G6 | Duplicates: one row per key is kept. A dropped row is marked `EXACT_DUPLICATE` (same values as the kept row), `SUPERSEDED_VERSION` (an older version of the same patient) or `DUPLICATE_KEY_CONFLICT` (same service, encounter or line ID with different values; the first row in the file is kept). | see below (no key conflicts in this data) |

## Patients (`patients.csv`)

| Rule | What it does | Reject reason | Rows hit |
|---|---|---|---|
| P1 | A blank `patient_id` is invalid. | `P1_BLANK_PATIENT_ID` | 2 |
| P2 | `patient_category` is matched to **SelfPay, Insured or Corporate**, ignoring case, spaces and hyphens (`SELF PAY`, `Self-Pay`, `selfpay` all become `SelfPay`). Any other value is rejected. `last_updated` must be a valid timestamp. A date of birth or registration date that is present must be valid. Gender and city are put in Title Case. Email is lower-cased. | `P2_INVALID_PATIENT_CATEGORY`, `P2_INVALID_LAST_UPDATED`, `P2_INVALID_DATE_OF_BIRTH`, `P2_INVALID_REGISTRATION_DATE` | 0 (26 category values were fixed by standardising) |
| P3 | A patient that appears more than once: the row with the **latest `last_updated`** is the current record. If two rows have the same `last_updated`, the one earlier in the file is kept. | `SUPERSEDED_VERSION` (6), `EXACT_DUPLICATE` (5) | 11 |

Result: 113 rows read, **100 patients accepted**, 13 rejected.

Example: PT017 appears as Insured (last updated 2024-02-04) and as Corporate (last updated 2026-03-01). The current record is Corporate, so KPI 4 counts PT017 as Corporate.

## Services (`services.csv`)

| Rule | What it does | Reject reason | Rows hit |
|---|---|---|---|
| S1 | `service_id` and `department` must not be blank. Department and category are put in Title Case (`radiology` becomes `Radiology`, `pharmacy` becomes `Pharmacy`). | `S1_BLANK_SERVICE_ID`, `S1_BLANK_DEPARTMENT` | 0 (4 department values fixed) |
| S2 | One row per `service_id` (the first in the file). | `EXACT_DUPLICATE` | 2 (SV005, SV010) |

Result: 22 rows read, **20 services accepted**, 2 rejected.

## Encounters (`encounters.csv`)

| Rule | What it does | Reject reason | Rows hit |
|---|---|---|---|
| E1 | `encounter_id` and `hospital_id` must not be blank. | `E1_BLANK_ENCOUNTER_ID`, `E1_BLANK_HOSPITAL_ID` | 0 |
| E2 | `encounter_type` must be Inpatient, Outpatient or Emergency and `encounter_status` must be Completed, Discharged, Open or Cancelled (any case). `admit_timestamp` must be valid. A discharge time that is given must be valid (a blank discharge is allowed). | `E2_INVALID_ENCOUNTER_TYPE`, `E2_INVALID_ENCOUNTER_STATUS`, `E2_INVALID_ADMIT_TIMESTAMP`, `E2_INVALID_DISCHARGE_TIMESTAMP` | 0 (40 type and 24 status values fixed) |
| E3 | The patient must exist in silver patients. Discharge must not be before admission. Admission must not be after the reporting cutoff (30 June 2026 23:59:59). | `E3_UNKNOWN_PATIENT` (EN9001-EN9005), `E3_DISCHARGE_BEFORE_ADMIT` (EN9006-EN9008), `E3_ADMIT_AFTER_CUTOFF` | 8 |
| (dup) | One row per `encounter_id` (the first in the file). | `EXACT_DUPLICATE` | 6 |
| **E4** | **Eligible encounter** (used by every KPI): a valid encounter (passed E1-E3) whose status is **Completed or Discharged**, admitted on or before the cutoff and discharged on or before the cutoff. Open and Cancelled encounters stay in `fct_encounter` with `is_eligible = false`. | not a reject: a flag in gold | 168 eligible, 26 not eligible (21 Cancelled, 5 Open) |

Result: 208 rows read, **194 encounters accepted**, 14 rejected.

`dim_hospital` is built from the accepted encounters: one row per `hospital_id` (6 hospitals). If a hospital's name, city or region ever differed between rows, the values on its most recent encounter would be used. In this data they never differ.

## Billing lines (`encounter_services.csv`)

| Rule | What it does | Reject reason | Rows hit |
|---|---|---|---|
| L1 | `encounter_service_id` must not be blank. | `L1_BLANK_LINE_ID` | 0 |
| L2 | `service_date` must be a valid date, on or before the cutoff. `quantity` must be a whole number above 0. `unit_price` has `Rs.`, `₹`, `INR`, commas and spaces removed and must then be a number of 0 or more. A blank `discount_pct` means 0%; it must be between 0 and 100. | `L2_INVALID_SERVICE_DATE`, `L2_INVALID_QUANTITY`, `L2_NON_POSITIVE_QUANTITY` (4), `L2_INVALID_UNIT_PRICE`, `L2_NEGATIVE_UNIT_PRICE` (3), `L2_INVALID_DISCOUNT`, `L2_DISCOUNT_OUT_OF_RANGE` (3, all 120%), `L2_SERVICE_AFTER_CUTOFF` | 10 (56 prices written with Rs./₹ were cleaned, 21 blank discounts set to 0) |
| **L3** | **Line charge** = quantity × unit_price × (1 − discount_pct / 100), rounded to 2 decimals, **half up**. Exact decimal maths is used (no floating point). | not a reject: the `line_charge` column | all 531 accepted lines |
| L4 | The encounter must be an accepted encounter, and the service must exist. We tell apart an encounter that never existed (`L4_UNKNOWN_ENCOUNTER`, EN8001-EN8004) from one that existed but was rejected by E3 (`L4_ENCOUNTER_REJECTED`, lines of EN9001-EN9008). The service date must fall between the admission date and the discharge date (if there is one). | `L4_UNKNOWN_ENCOUNTER` (4), `L4_ENCOUNTER_REJECTED` (16), `L4_UNKNOWN_SERVICE` (3, SV999), `L4_SERVICE_BEFORE_ADMIT`, `L4_SERVICE_AFTER_DISCHARGE` | 23 |
| (dup) | One row per `encounter_service_id` (the first in the file). | `EXACT_DUPLICATE` | 8 |

Result: 572 rows read, **531 lines accepted**, 41 rejected.

## Summary

| File | Read | Accepted | Rejected |
|---|---|---|---|
| patients.csv | 113 | 100 | 13 |
| services.csv | 22 | 20 | 2 |
| encounters.csv | 208 | 194 | 14 |
| encounter_services.csv | 572 | 531 | 41 |
