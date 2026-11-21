# Assumptions, and how rejected records affect the results

## Assumptions

1. **Missing rule list.** The document refers to rules E4 and L3 but does not define them, and the data pack extras (Data_Dictionary.csv, Dataset_Manifest.json, README) were not supplied. We wrote our own rules (see [CLEANSING_RULES.md](CLEANSING_RULES.md)) and kept the IDs E4 = eligible encounter and L3 = line charge.
2. **Eligible encounter (E4)** = valid encounter with status Completed or Discharged, admitted and discharged on or before 30 June 2026 23:59:59. Open encounters are still running and Cancelled ones should not be billed, so both are left out of the KPIs.
3. **Line charge (L3)** = quantity × unit_price × (1 − discount/100), rounded half up to 2 decimals. Totals are sums of the rounded line charges.
4. **Blank discount** means no discount (0%).
5. **Currency text.** `Rs.`, `₹`, `INR` and thousands commas in `unit_price` are formatting only. All amounts are INR without tax.
6. **Bad amounts are rejected, not fixed.** A negative price, a quantity of 0 or less, or a discount over 100% is treated as a data error and quarantined. We do not guess a value (for example, we do not flip a negative sign), because a guess could put wrong money into finance reports.
7. **Lines of rejected encounters are rejected too.** If an encounter fails a rule (unknown patient, discharge before admission), its billing lines cannot be linked to a valid hospital visit, so they are quarantined with `L4_ENCOUNTER_REJECTED`.
8. **Current patient category.** KPI 4 uses the category on the patient's current record (latest `last_updated`), for all of that patient's encounters, as the document asks.
9. **KPI 4 "number of patients"** is shown two ways: `patients` = all current patients in the category; `patients_with_eligible_encounters` = those who had at least one eligible encounter.
10. **Encounters without billing lines** would count as a bill of 0 in KPI 2, 3 and 4. (In this data every eligible encounter has at least one line.)
11. **Each batch is a full extract.** Silver and gold are rebuilt from one batch with overwrite. Bronze keeps every batch side by side (one partition per `batch_id`).
12. **Duplicates:** when two rows have the same key and the same values, the first one in the file is kept. For patients the latest `last_updated` wins.
13. **Privacy.** Names, email and phone stay in silver only. Gold tables and KPI outputs contain `patient_id` but no names, emails or phone numbers. A test checks this.
14. **Stretch KPIs.** The document mentions two optional stretch KPIs but does not define them. We added:
    - **KPI 5**: average and maximum inpatient length of stay (days) per hospital.
    - **KPI 6**: revenue mix by hospital region and service category, with each category's share of its region's revenue.

## How rejected and excluded records affect the results

Reported billed revenue (eligible encounters only): **INR 2,537,703.45**. The same total comes out of KPI 1, KPI 2, KPI 4 and KPI 6, and a test checks that they agree.

### Money that is not in the KPIs

| What | Lines | Face value (INR) | Why it is excluded | If we had included it |
|---|---|---|---|---|
| Valid lines on **Open** encounters | 23 | 163,060.60 | Visit not finished (E4) | Revenue would be about 6.4% higher. This money will show up in a later batch once the encounters close. |
| Valid lines on **Cancelled** encounters | 9 | 7,834.65 | Cancelled visits are not billed (E4) | Finance may want to review why cancelled visits have charges. |
| **Duplicate** billing lines | 8 | 107,788.65 | Same line sent twice | Revenue would be overstated by 107,788.65 (double counting). |
| Lines of **rejected encounters** (EN9001-EN9008) | 16 | 29,518.70 | Unknown patient or discharge before admission | These visits cannot be trusted or linked to a patient. |
| Lines of **unknown encounters** (EN8001-EN8004) | 4 | 2,798.05 | Encounter does not exist | No hospital or patient to report them under. |
| Lines for **unknown service** SV999 | 3 | 3,349.00 | Service not in the catalogue | No department to report them under (KPI 1). |
| **Negative quantity** (-1) | 4 | -3,133.25 | Looks like reversals or typing errors | Revenue would be lower by 3,133.25. |
| **Negative price** (-500) | 3 | -5,350.00 | Not a valid price | Revenue would be lower by 5,350.00. |
| **Discount of 120%** | 3 | -5,686.20 | A discount over 100% gives a negative charge | Revenue would be lower by 5,686.20. |

("Face value" = the line charge you would get by using the row exactly as written.)

### Effect on counts

- **Patients:** 2 rows with no patient_id are dropped. Their encounters, if any, could not be linked, so they would show up as `E3_UNKNOWN_PATIENT`. 11 repeated patient rows are removed, so each patient is counted once in KPI 4.
- **Category changes:** 6 patients changed category over time (for example PT017 Insured to Corporate, PT063 SelfPay to Insured). All their eligible encounters count under the current category.
- **Encounters:** 6 duplicate rows removed (they would have inflated encounter counts and average bills). 8 encounters rejected: 5 for unknown patients (PT901-PT905) and 3 where discharge is before admission.
- **Hospitals:** all 6 hospitals still appear in KPI 2 after cleansing.

### What finance should know

- The 32 valid lines on Open or Cancelled encounters (INR 170,895.25) are **not lost**: they are in `gold.fct_billing_line` and can be reported separately.
- Every quarantined row has `source_file` and `source_row_num`, so the source system team can fix it at the source and send it again in a new batch.
