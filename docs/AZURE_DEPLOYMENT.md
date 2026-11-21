# Running the pipeline on Azure

Chosen platform: **Azure**.

| Capability | Service used |
|---|---|
| Landing and lake storage | Azure Data Lake Storage Gen2 (one storage account, hierarchical namespace on) |
| Cleansing and transformation (SQL + PySpark) | Azure Databricks (Runtime 15.4 LTS: Spark 3.5, Delta Lake) |
| Curated tables and KPI queries | Delta Lake tables, queried with Databricks SQL |
| Workflow and orchestration | Azure Data Factory pipeline `pl_carevista_daily` |
| Failure alerts (optional) | Azure Monitor alert on the Data Factory "Failed pipeline runs" metric |

> **Status:** the code, notebooks and ADF pipeline definition are ready, and the same code is tested end to end on local Spark with Delta Lake (see [TEST_REPORT.md](TEST_REPORT.md)). It has **not** been deployed to an Azure subscription from here, because that needs your Azure account. Follow the steps below to deploy it.

## 1. Storage layout

One ADLS Gen2 account, for example `carevistalake`, with two containers:

```
staging/                                   <- source systems drop files here
  carevista/2026-06-30/patients.csv, services.csv, encounters.csv, encounter_services.csv

lake/carevista/
  landing/batch_id=B20260630/*.csv         <- unchanged copies (SHA-256 checked)
  bronze/<entity>/batch_id=.../            <- raw text + batch_id, source_file, source_row_num
  silver/<entity>/                         <- cleaned rows
  quarantine/<entity>/                     <- rejected rows + reject_reason
  gold/dim_*, fct_*, kpi*_*                <- star schema + KPI tables
  audit/pipeline_audit, audit/run_history  <- row counts and every task attempt
```

Landing, bronze, silver, gold, quarantine and audit are separate folders, as the brief allows ("containers, buckets or folders").

## 2. Create the resources (Azure CLI)

```bash
RG=rg-carevista
LOC=centralindia
SA=carevistalake            # must be globally unique
az group create -n $RG -l $LOC
az storage account create -n $SA -g $RG -l $LOC --sku Standard_LRS --kind StorageV2 --hns true
az storage container create --account-name $SA -n staging --auth-mode login
az storage container create --account-name $SA -n lake    --auth-mode login

# Upload the four source files to staging (unchanged)
az storage blob upload-batch --account-name $SA -d staging/carevista/2026-06-30 \
  -s ./data/source --pattern "*.csv" --auth-mode login

az databricks workspace create -n dbw-carevista -g $RG -l $LOC --sku premium
az datafactory create -n adf-carevista -g $RG -l $LOC
```

## 3. Give access

- **Databricks to storage:** create a Unity Catalog storage credential + external location for `abfss://lake@<sa>.dfs.core.windows.net/` and `abfss://staging@<sa>.dfs.core.windows.net/` (or, on a non-UC workspace, a service principal with the *Storage Blob Data Contributor* role and the matching `fs.azure.account.*` Spark settings).
- **Data Factory to Databricks:** in the Databricks workspace, give the Data Factory managed identity the *Contributor* role (or add it as a workspace user). The linked service uses `authentication: MSI`.

## 4. Put the code in Databricks

In Databricks: **Workspace > Create > Git folder**, and point it at this repository. The notebooks in `notebooks/databricks/` add `src/` to the Python path, so no package install is needed.

Fill in the placeholders:
- `orchestration/adf/linkedService/ls_azure_databricks.json`: workspace URL and resource ID.
- `orchestration/adf/pipeline/pl_carevista_daily.json`: the notebook path (`/Workspace/Repos/<your-user>/carevista/...`) and the default `input_path` / `lake_root` with your storage account name.

## 5. Deploy the Data Factory pipeline

```bash
az datafactory linked-service create -g $RG --factory-name adf-carevista -n ls_azure_databricks \
  --properties @orchestration/adf/linkedService/ls_azure_databricks.json   # use the "properties" object
az datafactory pipeline create -g $RG --factory-name adf-carevista -n pl_carevista_daily \
  --pipeline @orchestration/adf/pipeline/pl_carevista_daily.json          # use the "properties" object
```

(Or in ADF Studio: **Manage > Git configuration**, link this repo, and the JSON files are picked up.)

The pipeline has **four activities that run in order**: `01_Landing -> 02_Bronze -> 03_Silver -> 04_Gold`.
Each one:
- runs a Databricks notebook on a job cluster,
- receives `input_path`, `batch_id` and `lake_root` as parameters,
- has **retry = 1** (60 seconds between attempts),
- starts only if the previous one succeeded.

## 6. Run it and collect evidence

```bash
az datafactory pipeline create-run -g $RG --factory-name adf-carevista -n pl_carevista_daily \
  --parameters '{"batch_id":"B20260630","input_path":"abfss://staging@carevistalake.dfs.core.windows.net/carevista/2026-06-30","lake_root":"abfss://lake@carevistalake.dfs.core.windows.net/carevista"}'
```

1. **Successful run:** ADF Studio > Monitor > Pipeline runs shows all four activities green. Each activity's *Output* contains the notebook's row counts (from `dbutils.notebook.exit`).
2. **Rerun of the same batch:** start the same run again with the same `batch_id`. Then run `sql/databricks/02_evidence_queries.sql`: the counts and KPI totals are identical, and bronze still holds 113 / 22 / 208 / 572 rows for the batch (not double).
3. **Optional failed run + retry:** temporarily set `lake_root` to a path the cluster cannot write to, or stop the cluster during `03_Silver`; the activity shows attempt 1 failed and attempt 2 (the retry) runs.
4. **Row counts:** `carevista_ops.pipeline_audit` (after running `sql/databricks/01_register_tables.sql`).

## 7. Optional: failure alert

Azure Monitor > Alerts > Create > scope `adf-carevista` > signal **Failed pipeline runs metrics** (`PipelineFailedRuns`) > condition `> 0` over 5 minutes > action group with an email. This alerts the team when a run fails even after the retry.

## Same code on GCP or AWS

Only the paths and the orchestrator change: use `gs://...` with Dataproc + Cloud Composer, or `s3://...` with AWS Glue / EMR + Step Functions. The Python package and SQL files need no changes.
