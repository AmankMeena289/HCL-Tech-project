# CareVista Healthcare Analytics: Project Overview and Architecture

This document explains, in plain language:

1. [What the project has to do](#1-what-the-project-has-to-do-the-requirements)
2. [The architecture](#2-the-architecture-big-picture)
3. [How the pipeline works, step by step](#3-how-the-pipeline-works-step-by-step)
4. [The data model (star schema)](#4-the-data-model-star-schema)
5. [How the KPIs are calculated](#5-how-the-kpis-are-calculated)
6. [How the workflow runs, retries and reruns](#6-how-the-workflow-runs-retries-and-reruns)
7. [Audit, monitoring and privacy](#7-audit-monitoring-and-privacy)
8. [How we test it](#8-how-we-test-it)
9. [Where each piece of code lives](#9-where-each-piece-of-code-lives)
10. [How to run it](#10-how-to-run-it)
11. [Requirement checklist](#11-requirement-checklist)
12. [Limits and next steps](#12-limits-and-next-steps)

---

## 1. What the project has to do (the requirements)

### The business problem

CareVista Health Network runs **6 hospitals** in North, South and West India. Three separate systems send data files:

| System | File | What is in it |
|---|---|---|
| Patient registration | `patients.csv` (113 rows) | Who the patients are, and their payment category (SelfPay, Insured, Corporate) |
| Hospital admissions | `encounters.csv` (208 rows) | Each hospital visit: which patient, which hospital, type, status, admit and discharge time |
| Billing | `services.csv` (22 rows) | The price list of services (catalogue) and their department |
| Billing | `encounter_services.csv` (572 rows) | Each billed line: which visit, which service, quantity, price, discount |

These files are **messy**. Nobody checks them before they arrive:

- Some rows are repeated (duplicates).
- Some patients appear twice with different details.
- Some IDs are blank.
- Dates come in two formats (`2026-05-02` and `02/05/2026`).
- Prices sometimes include text such as `Rs. 906` or `₹1,234.50`.
- Text is written in different ways (`SELF PAY`, `Self-Pay`, `selfpay`).
- Some values are impossible: quantity -1, price -500, discount 120%, discharge before admission.
- Some rows point to patients, visits or services that do not exist.

Finance and operations want reliable numbers on **billed revenue**, **how many patients each hospital treats** and **which patient groups bill the most**. To get those numbers, we first have to clean the data.

### What we must deliver

| # | Requirement (from the brief) | In simple words |
|---|---|---|
| R1 | Use **one cloud**: Azure, GCP or AWS | We chose **Azure** |
| R2 | Copy the 4 files **unchanged** into a landing area in cloud storage | Keep an exact copy of what arrived |
| R3 | Clean the data with **SQL and PySpark** | Python on Spark for cleaning, SQL for KPIs |
| R4 | Layers: **bronze → silver → gold** | Raw → cleaned → ready for reports |
| R5 | Add `batch_id` and `source_file` to every bronze row | Every row knows which load and file it came from |
| R6 | Separate places for landing, bronze, silver, gold, **quarantine** and **audit** data | Bad rows and counts are stored apart |
| R7 | Build a simple **star schema** | Fact and dimension tables |
| R8 | Deliver **4 required KPIs** (+ 2 optional stretch KPIs) | Revenue, encounters, top patients, category profile |
| R9 | Use **eligible encounters only** (rule E4) and **line charge** amounts (rule L3) | Only finished, valid visits count |
| R10 | Gold and quarantine written with **overwrite**; a rerun gives **the same result** | Running twice must not double anything |
| R11 | **Parameterise** the input path and `batch_id` | No hard-coded paths |
| R12 | **Audit table**: rows read, accepted, rejected for each file | Counts prove nothing was lost |
| R13 | A **workflow** with 3-4 tasks in order, **1 retry per task** | Azure Data Factory pipeline |
| R14 | Show a successful run and a **rerun** that changes nothing (a failed run + retry is optional) | Evidence |
| R15 | **No names, emails or phone numbers** in KPI outputs | Privacy |
| R16 | **Document** the cleansing decisions, assumptions and the effect of rejected rows | The docs folder |

Fixed facts from the brief:

- The reporting cutoff is **30 June 2026, 23:59:59**.
- All times are already **Asia/Kolkata local time**, so we do no time-zone conversion.
- Amounts are **INR, without tax**.
- The original files must stay unchanged.

---

## 2. The architecture (big picture)

### 2.1 On Azure (target platform)

```
                         ┌──────────────────────────────────────────────┐
                         │        Azure Data Factory (orchestrator)      │
                         │        pipeline: pl_carevista_daily           │
                         │  parameters: input_path, batch_id, lake_root  │
                         │                                              │
                         │  01_Landing ─► 02_Bronze ─► 03_Silver ─► 04_Gold
                         │   (retry 1)    (retry 1)    (retry 1)   (retry 1)
                         └──────┬───────────┬───────────┬──────────┬────┘
                                │ runs notebooks on a Databricks job cluster
                                ▼           ▼           ▼          ▼
┌────────────────┐     ┌──────────────────────────────────────────────────┐
│ Source systems │     │            Azure Databricks (Spark 3.5)           │
│ registration,  │     │   Python package "carevista" (PySpark + SQL)      │
│ admissions,    │     └──────────────────────┬───────────────────────────┘
│ billing        │                            │ reads / writes Delta Lake
└──────┬─────────┘                            ▼
       │ drop CSVs   ┌──────────────────────────────────────────────────────┐
       ▼             │        Azure Data Lake Storage Gen2                   │
┌──────────────┐     │  lake/carevista/                                      │
│ staging/     │────►│   landing/  bronze/  silver/  gold/  quarantine/ audit/│
│ (container)  │     └───────────────────────────┬──────────────────────────┘
└──────────────┘                                 │
                                                 ▼
                     ┌──────────────────────────────────────────────────────┐
                     │ Databricks SQL: analysts query gold KPI tables         │
                     │ Azure Monitor (optional): alert when a run fails       │
                     └──────────────────────────────────────────────────────┘
```

### 2.2 Technology choices and why

| Need | Choice | Why |
|---|---|---|
| Storage | **ADLS Gen2** | Required for Azure. Folders behave like a real file system. |
| Processing | **Azure Databricks** + **PySpark** | Required for Azure. The same Spark code runs on any cloud and on a laptop. |
| Table format | **Delta Lake** | The brief prefers it. It gives safe overwrites, "replace only this batch" writes, and a history of changes. |
| KPI logic | **Spark SQL files** (`.sql`) | Easy to read and review, and they run unchanged in Databricks SQL. |
| Orchestration | **Azure Data Factory** | Required for Azure. It provides ordered activities, parameters, retries and run history. |
| Alerts (optional) | **Azure Monitor** | The brief names it as the Azure monitoring service. |

### 2.3 On a laptop (used for development and testing)

The same Python package runs locally with **Spark 3.5.3 + Delta Lake 3.2.1** (in WSL Ubuntu on this machine). Two things replace the cloud services:

- a folder `lake/` replaces ADLS;
- the Python runner `pipeline.py` replaces Data Factory, with the same 4 tasks, the same parameters and the same retry rule.

This is how the whole pipeline was proven to work end to end, with 126 automated tests.

```
data/source/*.csv ──► python -m carevista.pipeline ──► lake/{landing,bronze,silver,gold,quarantine,audit}
                      --input-path --batch-id               └──► reports/ (KPI CSVs + HTML report)
```

---

## 3. How the pipeline works, step by step

```
 STAGED FILES                                                                 
 patients.csv, services.csv, encounters.csv, encounter_services.csv           
      │                                                                        
      ▼  Task 1: LANDING ─ exact byte copy + SHA-256 check                     
 landing/batch_id=B20260630/*.csv                                              
      │                                                                        
      ▼  Task 2: BRONZE ─ load as text, add batch_id, source_file, source_row_num
 bronze/<entity>  (Delta, partitioned by batch_id)                             
      │                                                                        
      ▼  Task 3: SILVER ─ clean, check, standardise, remove duplicates          
 silver/<entity>  (good rows)        quarantine/<entity> (bad rows + reason)   
      │                                                                        
      ▼  Task 4: GOLD ─ star schema + KPI SQL                                   
 gold/dim_*, gold/fct_*, gold/kpi1..kpi6                                       
                                                                               
 Every task also writes counts to audit/pipeline_audit and audit/run_history  
```

### Task 1: Landing (`src/carevista/landing.py`)

- **Input:** `input_path` (the folder holding the 4 staged files).
- **What it does:** copies each file byte for byte into `landing/batch_id=<batch_id>/`. It then reads both the original and the copy and compares their size and **SHA-256 fingerprint**. If they differ, the task fails.
- **Why:** it proves the landed files are exactly what arrived, and the originals are never touched.
- **Output:** 4 files in landing, plus 4 audit rows (bytes and SHA-256 of each file).

### Task 2: Bronze (`src/carevista/bronze.py`)

- **What it does:**
  1. Checks that each file's header has exactly the expected columns. If not, it stops with a clear error, so a changed file layout cannot slip through.
  2. Reads every column **as text**. Nothing is cleaned yet, so bronze is a faithful copy.
  3. Adds lineage columns:
     - `batch_id`: which load the row came from;
     - `source_file`: which file;
     - `source_row_num`: which line in that file;
     - `_corrupt_record`: the raw line, if it had the wrong number of columns.
  4. Writes to Delta, **replacing only this batch's rows**. Other batches stay; a rerun does not add a second copy.
- **Output:** `bronze/patients` (113 rows), `bronze/services` (22), `bronze/encounters` (208), `bronze/encounter_services` (572).

### Task 3: Silver (`src/carevista/silver.py` + `src/carevista/rules.py`)

This is where the cleaning happens. Each file is processed in this order, because later files refer to earlier ones:

```
patients ──► services ──► encounters (need valid patients) ──► billing lines (need valid encounters + services)
```

For each row the job does three things:

1. **Standardise** the values:
   - trim spaces;
   - read both date formats;
   - remove `Rs.`/`₹`/commas from prices;
   - match category, type and status spellings;
   - put departments in Title Case;
   - treat a blank discount as 0.
2. **Check** the row against every rule and collect *all* failed rules into a list, for example `L2_NON_POSITIVE_QUANTITY; L4_UNKNOWN_SERVICE`.
3. **Remove duplicates** among the rows that passed. For patients, the row with the latest `last_updated` wins. Otherwise the first row in the file wins.

Then:

- rows with **no problems** go to `silver/<entity>`, typed and clean;
- rows **with problems** go to `quarantine/<entity>`, with the original text unchanged, the lineage columns and `reject_reason`;
- the job checks that **read = accepted + rejected** and fails if not. The counts go into the audit table.

The rules in short (full list in [CLEANSING_RULES.md](CLEANSING_RULES.md)):

| File | Main rules | Kept | Rejected |
|---|---|---|---|
| Patients | P1 blank ID rejected · P2 category must be SelfPay/Insured/Corporate · P3 latest `last_updated` is current | 100 | 13 (2 blank ID, 6 older versions, 5 exact duplicates) |
| Services | S1 ID and department required, department standardised · S2 one row per service | 20 | 2 duplicates |
| Encounters | E1 IDs required · E2 valid type, status, timestamps · E3 patient must exist, discharge not before admit, admit not after cutoff | 194 | 14 (6 duplicates, 5 unknown patient, 3 discharge before admit) |
| Billing lines | L1 ID required · L2 valid date, quantity > 0, price ≥ 0, discount 0-100 · L4 encounter and service must exist, date within the visit | 531 | 41 (16 on rejected visits, 8 duplicates, 4 unknown visits, 4 negative quantity, 3 negative price, 3 discount 120%, 3 unknown service) |

Two rules are not rejections; they are calculations used by the KPIs:

- **L3 Line charge** = quantity × unit_price × (1 − discount_pct / 100), rounded to 2 decimals **half up**. The maths uses exact decimals, never floating point.
- **E4 Eligible encounter** = a valid encounter that is **Completed or Discharged**, admitted and discharged on or before the cutoff. Open and Cancelled visits are kept but flagged `is_eligible = false`.

**Time handling:** timestamps are stored as *timestamp without time zone*, so `01/06/2026 11:02` is stored as 2026-06-01 11:02 on any server, in any time zone.

### Task 4: Gold (`src/carevista/gold.py` + `src/carevista/sql/*.sql`)

1. Builds the star schema from silver (see section 4).
2. Runs the six KPI SQL files on those tables.
3. Writes every gold table and KPI table with **overwrite**, so a rerun gives exactly the same tables.

---

## 4. The data model (star schema)

```
                     ┌──────────────────────┐
                     │     dim_patient      │  100 rows
                     │ patient_id (PK)      │  (no names, email, phone)
                     │ gender, city         │
                     │ patient_category     │
                     │ date_of_birth        │
                     │ registration_date    │
                     │ record_last_updated  │
                     └──────────┬───────────┘
                                │ 1
                                │
                                │ many
┌──────────────────┐   ┌────────┴─────────────────┐       ┌───────────────────┐
│   dim_hospital   │ 1 │      fct_encounter       │       │    dim_service    │  20 rows
│ hospital_id (PK) ├───┤ encounter_id (PK)        │       │ service_id (PK)   │
│ hospital_name    │ m │ patient_id (FK)          │       │ service_name      │
│ hospital_city    │   │ hospital_id (FK)         │       │ service_category  │
│ hospital_region  │   │ encounter_type, status   │       │ department        │
└──────────────────┘   │ admit/discharge_timestamp│       └─────────┬─────────┘
      6 rows           │ admit_date               │                 │ 1
                       │ length_of_stay_hours     │                 │
                       │ is_eligible  (rule E4)   │                 │ many
                       └────────┬─────────────────┘                 │
                                │ 1                                 │
                                │ many                              │
                       ┌────────┴─────────────────────────────────┴┐
                       │            fct_billing_line                │  531 rows
                       │ encounter_service_id (PK)                  │
                       │ encounter_id (FK), service_id (FK)         │
                       │ service_date, service_month                │
                       │ quantity, unit_price, discount_pct         │
                       │ gross_amount, line_charge  (rule L3)       │
                       └────────────────────────────────────────────┘
                       194 rows in fct_encounter (168 eligible)
```

- `dim_hospital` comes from the hospital columns in the encounters file (there is no hospital file).
- Every foreign key points to an existing row. A test checks there are no orphans.

---

## 5. How the KPIs are calculated

All KPIs use **eligible encounters only** (E4) and **line_charge** (L3). They are plain SQL files in `src/carevista/sql/`.

| KPI | Question it answers | How |
|---|---|---|
| **1** Revenue by department per month | Which departments bring in the most money, month by month? | Sum `line_charge` of lines on eligible encounters, grouped by `service_month` and `department`. |
| **2** Encounters and average bill by hospital and type | How busy is each hospital, and how big is a typical bill? | Per hospital and encounter type: count eligible encounters, sum their bills, and divide (rounded half up to 2 decimals). A visit with no lines would count as a bill of 0. |
| **3** Top 10 patients | Which patients bill the most? | Sum per patient across eligible encounters. Rank highest first; a tie goes to the lower `patient_id`. Shows `patient_id` only. |
| **4** Patient category profile | Which payment group generates the most billing? | For SelfPay, Insured and Corporate (each patient's *current* category): number of patients, eligible encounters, billed total and average bill. The average is **NULL, not 0**, when a category has no eligible encounters. |
| **5** (stretch) Inpatient length of stay | How long do inpatients stay at each hospital? | Average and maximum (discharge − admit) in days, for eligible inpatient visits. |
| **6** (stretch) Revenue mix by region | What share of each region's revenue comes from each service category? | Revenue per region and category, and its % of the region total. |

A built-in cross-check: KPI 1, 2, 4 and 6 must all add up to the **same total revenue (INR 2,537,703.45)**. KPI 2 and 4 must have the same number of eligible encounters (168).

---

## 6. How the workflow runs, retries and reruns

### The workflow

| Order | Task | Azure (Data Factory activity → Databricks notebook) | Local (`pipeline.py`) |
|---|---|---|---|
| 1 | Landing | `01_Landing` → `notebooks/databricks/00_landing.py` | `landing.run` |
| 2 | Bronze | `02_Bronze` → `01_bronze.py` | `bronze.run` |
| 3 | Silver | `03_Silver` → `02_silver.py` | `silver.run` |
| 4 | Gold | `04_Gold` → `03_gold.py` | `gold.run` |

- **Parameters:** `input_path` and `batch_id` (plus `lake_root`, which says where the lake is). In ADF they are pipeline parameters, passed to each notebook as widgets. Locally they are command-line flags.
- **Order:** each task starts only if the previous one succeeded.
- **Retry:** each task gets **1 retry**. If the retry also fails, the run stops and later tasks do not run.
- **Run history:** every attempt (task, attempt number, status, start, end, error message) is written to `audit/run_history`. In Azure, the ADF Monitor page also shows it.

### Why a rerun changes nothing (idempotency)

| Layer | Write method | Effect of running the same batch again |
|---|---|---|
| Landing | Copy to `landing/batch_id=<id>/` with overwrite | Same files, same SHA-256 |
| Bronze | Delta "replace where batch_id = X" | That batch's rows are replaced, not added. Still 113 patient rows, not 226 |
| Silver / Quarantine | Full overwrite | Same rows |
| Gold / KPIs | Full overwrite | Same rows |
| Audit counts | Replace this batch + step | One set of counts per batch |
| Run history | Append (on purpose) | It is a log, so every run is kept |

Duplicate handling uses fixed tie-breakers (`last_updated`, then file row number), so the same input always picks the same winner.

This was proven three ways:

- a test compares every table before and after a rerun;
- a test compares them before and after a forced failure plus retry;
- the logs in `evidence/` show both.

---

## 7. Audit, monitoring and privacy

### Audit table (`audit/pipeline_audit`)

One row per batch, step and file, with these columns:

`batch_id | step | entity | source_file | rows_read | rows_accepted | rows_rejected | detail | recorded_at`

- For **landing**, `detail` holds the file size and SHA-256.
- For **silver**, `detail` lists how many rows each reject reason caught, for example `L2_NEGATIVE_UNIT_PRICE=3`.

### Tracing a rejected row

Every quarantined row carries `batch_id`, `source_file` and `source_row_num`, so anyone can open the original file and find the exact line. The `reject_reason` says what to fix.

### Monitoring

- **Locally:** console output, `audit/run_history` and the HTML report.
- **Azure:** ADF Monitor shows run status per activity, and each notebook returns its row counts in the activity output. Optionally, an **Azure Monitor** alert on `PipelineFailedRuns > 0` can email the team.

### Privacy

- Names, email addresses and phone numbers exist only in `silver/patients`.
- `dim_patient` and all KPI tables hold **no personal identifiers**, only `patient_id`.
- A test scans every gold table, by column name and by value, to make sure.

---

## 8. How we test it

There are **126 automated tests** (`./scripts/run_tests.sh`), and all of them pass.

| Level | File | Count | What it checks |
|---|---|---|---|
| Unit | `tests/test_rules.py` | 48 | Each cleaning function: dates, timestamps, prices, categories, rounding half up |
| Rule | `tests/test_silver_rules.py` | 15 | Each silver rule on small hand-made rows |
| KPI | `tests/test_kpi_sql.py` | 5 | Each KPI query on tiny tables with known answers (tie-break, NULL average, etc.) |
| Workflow | `tests/test_pipeline_runner.py` | 11 | Task order, retry once, stop after 2 failures, parameter checks, header check |
| End to end | `tests/test_pipeline_e2e.py` | 47 | Full run on the real data: counts, reasons, star schema, privacy, KPIs, rerun, retry |

The key idea: `tests/oracle.py` is a **second, independent implementation** of all the rules in plain Python and pandas. The Spark KPIs must match it exactly. For a wrong number to pass, the same mistake would have to be made twice, in two different ways.

Details: [TEST_REPORT.md](TEST_REPORT.md).

---

## 9. Where each piece of code lives

| Path | Purpose |
|---|---|
| `src/carevista/config.py` | File names, expected columns, cutoff, allowed values, zone paths, batch_id check |
| `src/carevista/rules.py` | Reusable cleaning functions (text, dates, timestamps, amounts, choices, line charge) |
| `src/carevista/landing.py` | Task 1: copy and verify files |
| `src/carevista/bronze.py` | Task 2: raw load with lineage |
| `src/carevista/silver.py` | Task 3: rules, quarantine, de-duplication, counts |
| `src/carevista/gold.py` | Task 4: star schema and KPI tables |
| `src/carevista/sql/kpi1..kpi6*.sql` | KPI queries |
| `src/carevista/audit.py` | Audit and run-history tables |
| `src/carevista/io.py` | Delta read/write (overwrite, replace one batch), file copy, SHA-256 |
| `src/carevista/spark.py` | Spark session settings (non-ANSI parsing, Asia/Kolkata, Delta) |
| `src/carevista/pipeline.py` | Local workflow runner (order, retry, run history, `--fail-once` demo) |
| `src/carevista/report.py` | KPI report as CSV, Markdown and HTML |
| `notebooks/databricks/` | One notebook per task, called by Data Factory |
| `orchestration/adf/` | Data Factory pipeline and Databricks linked service (JSON) |
| `sql/databricks/` | Register tables in Databricks SQL, plus evidence queries |
| `tests/` | All tests + `oracle.py` |
| `scripts/` | Set-up, run and test helpers (bash and PowerShell) |
| `docs/` | This file, rules, assumptions, Azure guide, test report |
| `reports/` | Latest KPI outputs |
| `evidence/` | Run logs and test results |

---

## 10. How to run it

**On this computer (WSL Ubuntu):**

```bash
bash scripts/setup_env.sh                          # once: Spark, Delta, pytest, Java 17
./scripts/run_local.sh B20260630                   # run the pipeline + write reports/
./scripts/run_local.sh B20260630                   # rerun: same results
./scripts/run_local.sh B20260630 --fail-once silver   # show a failure and a retry
./scripts/run_tests.sh                             # run all 126 tests
```

From Windows PowerShell, use `.\scripts\run_local.ps1` and `.\scripts\run_tests.ps1`.

**On Azure:** follow [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md):

1. create the storage account, Databricks and Data Factory;
2. upload the CSVs to `staging`;
3. link the repo in Databricks;
4. deploy the ADF JSON;
5. start the pipeline with `batch_id` and `input_path`.

---

## 11. Requirement checklist

| Req | Requirement | Done | How / where |
|---|---|---|---|
| R1 | One cloud platform | Yes | Azure: ADLS Gen2, Databricks, Delta, Data Factory |
| R2 | Files copied unchanged into landing | Yes | `landing.py` with SHA-256 check |
| R3 | SQL and PySpark | Yes | PySpark in bronze/silver/gold, SQL for KPIs |
| R4 | Bronze → silver → gold | Yes | Four tasks |
| R5 | `batch_id`, `source_file` in bronze | Yes | Plus `source_row_num` |
| R6 | Separate zones incl. quarantine and audit | Yes | `landing/ bronze/ silver/ gold/ quarantine/ audit/` |
| R7 | Star schema | Yes | 3 dimensions + 2 facts |
| R8 | 4 KPIs (+2 stretch) | Yes | `sql/kpi1..kpi6` |
| R9 | Eligible encounters (E4), line charge (L3) | Yes | `gold.build_fct_encounter`, `rules.line_charge` |
| R10 | Overwrite; rerun gives the same result | Yes | Tested before/after rerun |
| R11 | Parameterised input path and batch_id | Yes | CLI flags / ADF parameters |
| R12 | Audit: read, accepted, rejected | Yes | `audit/pipeline_audit`, with a read = accepted + rejected check |
| R13 | 3-4 ordered tasks, 1 retry each | Yes | ADF `pl_carevista_daily`, local runner |
| R14 | Successful run + rerun (+ optional fail/retry) | Yes (locally) | `evidence/run1..run3*.log` |
| R15 | No names, emails, phones in outputs | Yes | Not in gold at all; tested |
| R16 | Documentation | Yes | `docs/` |
| Optional | Data catalog registration | Ready | `sql/databricks/01_register_tables.sql` |
| Optional | Failure alert | Described | Azure Monitor alert in the deployment guide |

---

## 12. Limits and next steps

- **Not deployed to Azure yet.** It needs an Azure subscription. The code is tested locally on the same Spark and Delta versions that Databricks Runtime 15.4 LTS uses. Only the paths and the orchestrator change in the cloud.
- **Rules were defined by us.** The brief mentions rules E4 and L3 without listing them, and the data dictionary was not supplied. If the official rule list differs, the rules are kept in one place (`silver.py`, `rules.py`) and are easy to change.
- **Each batch is a full extract.** If the source systems later send only changes, silver would need a merge (Delta `MERGE`) instead of an overwrite.
- **Possible extensions:**
  - register tables in Unity Catalog;
  - a Power BI dashboard on the gold tables;
  - a monthly trend of revenue on Open encounters (INR 163,060.60 is waiting for those visits to close).
