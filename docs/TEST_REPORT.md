# Test report

**Result: 126 tests, 126 passed, 0 failed** (local Spark 3.5.3 + Delta Lake 3.2.1, Java 17, Python 3.12 on WSL Ubuntu).
Full list of tests with their results: [../evidence/test_results.txt](../evidence/test_results.txt).

Run them yourself with `./scripts/run_tests.sh` (or `.\scripts\run_tests.ps1` on Windows). They take about 4 minutes.

## How we know the KPIs are right

The end-to-end tests run the real pipeline on the supplied files. Then they compare the KPI tables with numbers from **`tests/oracle.py`**, a second implementation of the same rules written in plain pandas and Python `Decimal`. It shares no code with the pipeline. For a wrong number to pass, the same mistake would have to be made twice, in two different ways.

The tests also check that the total revenue is the same whichever KPI you add it up from (KPI 1 = KPI 2 = KPI 4 = KPI 6 = INR 2,537,703.45), and that the encounter counts in KPI 2 and KPI 4 agree (168).

## What is tested

| File | Tests | What it checks |
|---|---|---|
| `test_rules.py` | 48 | Each cleansing function on its own: trimming; both date formats (and that 04/01/2026 is 4 January); invalid dates; `Rs.` / `₹` / comma prices; negative and bad prices; category spelling variants (`SELF PAY`, `Self-Pay`, ...); department case; quantities; blank discount = 0; line charge rounding **half up** with exact decimals (e.g. 0.095 → 0.10, where floating point would give 0.09). |
| `test_silver_rules.py` | 15 | Each silver rule on small hand-made rows: latest `last_updated` wins; exact duplicate vs older version vs key conflict; blank patient_id; bad category; original text kept in quarantine with file and row number; department standardised; malformed row; unknown patient; discharge before admit; admit after cutoff; bad type or timestamp; Open encounter with blank discharge kept; every billing-line reject reason; several reasons listed together; currency text and line charge; duplicate lines. |
| `test_kpi_sql.py` | 5 | KPI SQL on tiny star schemas with known answers: ineligible encounters are left out; an encounter with no lines counts as 0; average rounded half up (100.01 / 3 = 33.34); top-10 ties broken by patient_id; no personal columns in KPI 3; **KPI 4 shows a NULL average (not 0) for a category with no eligible encounters**. |
| `test_pipeline_runner.py` | 11 | Workflow: tasks run in order; a failed task is retried once and the run continues; a task failing twice stops the run (later tasks do not run); batch_id is validated; zone paths; a changed file header stops the run; a row with extra columns is caught. |
| `test_pipeline_e2e.py` | 47 | Whole pipeline on the real data (details below). |

### End-to-end checks (`test_pipeline_e2e.py`)

- Landing files are byte-identical copies (SHA-256) and the original files are unchanged.
- Bronze has every physical row (113 / 22 / 208 / 572), each with batch_id, source_file and a unique row number.
- Audit: rows read = accepted + rejected for every file; accepted counts are 100 / 20 / 194 / 531 and match the oracle.
- Every bronze row ends up in exactly one place: silver or quarantine. Every quarantined row has a reason and points back to a bronze row.
- 13 known bad rows land in quarantine with the right reason (e.g. ES90001 negative quantity, ES90008 120% discount, ES90015 unknown service, EN9001 unknown patient, EN9006 discharge before admit, PT017 older version).
- PT017's current category is Corporate (latest `last_updated` wins).
- Timestamps keep their local clock time (`01/06/2026 11:02` is stored as 2026-06-01 11:02, no time-zone shift).
- Values are standardised (3 categories, 3 encounter types, 6 departments, no stray spaces).
- Gold: keys are unique, no orphan rows in the star schema, 6 hospitals, 168 eligible encounters and the E4 flag matches the status.
- **No names, emails or phone numbers** anywhere in gold or the KPI tables (checked by column name and by value).
- KPI 1, 2, 3 and 4 match the oracle exactly; totals reconcile across KPIs; stretch KPIs are sensible (shares add up to 100%).
- **Rerun of the same batch:** every bronze, silver, quarantine and gold table and the audit counts are identical before and after; bronze still has 113 patient rows for the batch (not 226).
- **Failed attempt + retry:** with silver forced to fail once, attempt 1 fails, attempt 2 succeeds, and the results are identical; run history records all attempts.

## Run evidence

| Log | Shows |
|---|---|
| [evidence/run1_first_run.log](../evidence/run1_first_run.log) | First successful run with row counts per step |
| [evidence/run2_rerun_same_batch.log](../evidence/run2_rerun_same_batch.log) | Rerun of the same batch: same counts |
| [evidence/run3_failure_then_retry.log](../evidence/run3_failure_then_retry.log) | Silver fails on attempt 1, succeeds on the retry, run completes |

The report ([reports/kpi_report.html](../reports/kpi_report.html)) ends with the run history table, listing every attempt of every task across the three runs.

## What was not tested here

- The Azure deployment itself (ADF pipeline, Databricks job cluster, ADLS paths). That needs an Azure subscription. The same Python and SQL code runs there unchanged; only the paths and the orchestrator differ.
