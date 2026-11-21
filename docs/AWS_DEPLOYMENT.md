# Running the pipeline on AWS

The pipeline was first designed for Azure (see [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md)). This guide covers the AWS deployment. The Python package in `src/carevista/` and the KPI SQL files are **unchanged**. Only the storage paths (`s3://`) and the orchestrator differ.

| Capability | Azure | AWS |
|---|---|---|
| Landing and lake storage | ADLS Gen2 containers | 3 S3 buckets: `staging`, `lake`, `artifacts` |
| Cleansing and transformation (SQL + PySpark) | Azure Databricks | AWS Glue 5.0 (Spark 3.5, Delta Lake via `--datalake-formats delta`) |
| Curated tables and KPI queries | Databricks SQL | Delta tables in the Glue Data Catalog, queried with Amazon Athena |
| Workflow and orchestration | Data Factory `pl_carevista_daily` | Step Functions state machine `carevista-daily` |
| Failure alert | Azure Monitor alert | SNS topic `carevista-pipeline-alerts`, published by the workflow |

Deployed to account `919315337648`, region **ap-southeast-2 (Sydney)**. Sydney is the only region the account's organization policy (SCP) allows for Glue, Step Functions, S3 and Athena.

## Files

```
deploy/aws/
  bootstrap_iam.sh         one-time: IAM user carevista-deployer + CLI profile "carevista" (run as an admin)
  deploy.sh                buckets, roles, Glue jobs, state machine, SNS, Athena (safe to rerun)
  run_pipeline.sh          start the workflow, wait, print every task attempt
  athena_register.sh       register gold + audit Delta tables in Athena and print check queries
  glue_job.py              Glue entry point shared by the 4 jobs (--task landing|bronze|silver|gold)
  state_machine.asl.json   workflow definition (template)
  iam/*.json               trust and permission policies (templates)
  build_job_json.py, package_code.py   helpers used by deploy.sh
```

## Architecture

```
s3://carevista-<acct>-staging/carevista/2026-06-30/*.csv      <- source files, unchanged
            |
   Step Functions "carevista-daily"   (input: batch_id, input_path, lake_root, fail_once - all optional)
     01_Landing -> 02_Bronze -> 03_Silver -> 04_Gold          each = Glue job, Retry 1 x after 60 s
            |  any task fails twice -> SNS "carevista-pipeline-alerts" -> execution Failed
            v
s3://carevista-<acct>-lake/carevista/
  landing/batch_id=B20260630/*.csv    bronze/  silver/  quarantine/  gold/  audit/
  reports/kpi_report.html, kpi_report.md, kpi*.csv     <- written after gold
            |
   Athena (workgroup "carevista"): carevista_gold.*, carevista_ops.pipeline_audit / run_history
```

- **Code delivery.** `src/carevista` is zipped to `s3://…-artifacts/code/carevista.zip`. `glue_job.py` downloads and unpacks it to local disk, rather than importing from the zip, because `gold.py` reads the KPI `.sql` files from the package folder.
- **Retry.** Each Glue job has `MaxRetries = 0`, and the single retry is done by Step Functions, so both attempts are visible in the execution history. Every attempt is also written to `audit/run_history`. The attempt number is derived from earlier rows for the same `run_id` (the execution name) and task.
- **Rerun safety.** This is the same logic as on Azure. Bronze and audit replace only their own batch's rows, while silver, quarantine and gold are overwritten. Each Glue job allows one concurrent run. **Do not start two executions of the same batch at the same time.**

## IAM

| Identity | Type | Permissions |
|---|---|---|
| `carevista-deployer` | IAM user. Its access key is in the local CLI profile `carevista` | AWS managed `AWSGlueConsoleFullAccess`, `AWSStepFunctionsFullAccess`, `AmazonAthenaFullAccess`, `AmazonSNSFullAccess`, `CloudWatchLogsReadOnlyAccess`, plus an inline policy: IAM role management limited to `carevista-*` roles, and S3 limited to `carevista-*` buckets |
| `carevista-glue-role` | Role assumed by Glue | `AWSGlueServiceRole` plus inline S3: read staging and code, read/write the lake |
| `carevista-sfn-role` | Role assumed by Step Functions | Start, get and stop runs of `carevista-*` Glue jobs; publish to the alert topic |

The organization's SCP denies `iam:CreateGroup`, so `bootstrap_iam.sh` attaches the policies directly to the user. Where groups are allowed, it uses a `carevista-deployers` group instead.

## Deploy from scratch

```bash
aws login --region ap-southeast-2                        # an administrator login
bash deploy/aws/bootstrap_iam.sh                         # creates carevista-deployer + profile "carevista"
AWS_PROFILE=carevista bash deploy/aws/deploy.sh          # everything else (rerun after code changes)
```

## Run and collect evidence

```bash
AWS_PROFILE=carevista bash deploy/aws/run_pipeline.sh B20260630           # 1. successful run
AWS_PROFILE=carevista bash deploy/aws/athena_register.sh                  #    register tables + check totals
AWS_PROFILE=carevista bash deploy/aws/run_pipeline.sh B20260630           # 2. rerun of the same batch
AWS_PROFILE=carevista bash deploy/aws/run_pipeline.sh B20260630 silver    # 3. silver fails once, retry succeeds
```

Where to look:
- **Step Functions console** > `carevista-daily` > the execution: the graph view shows each task, and the event history shows the failed attempt and the retry.
- **Glue console** > Jobs > `carevista-0N-*` > Runs: the logs are in CloudWatch under `/aws-glue/jobs/output` and `/aws-glue/jobs/error`.
- **Athena** (workgroup `carevista`):
  ```sql
  SELECT * FROM carevista_ops.pipeline_audit WHERE batch_id = 'B20260630' ORDER BY step, source_file;
  SELECT * FROM carevista_ops.run_history ORDER BY started_at;
  SELECT * FROM carevista_gold.kpi1_revenue_by_department_month ORDER BY month, department;
  ```
- **KPI report**: `s3://carevista-919315337648-lake/carevista/reports/kpi_report.html`.

## Failure alert

The workflow publishes to `carevista-pipeline-alerts` when a task fails after its retry. To receive the alerts by email:

```bash
aws sns subscribe --profile carevista --topic-arn arn:aws:sns:ap-southeast-2:919315337648:carevista-pipeline-alerts \
  --protocol email --notification-endpoint you@example.com     # then click the confirmation link
```

## Cost and clean-up

Each run uses 4 short Glue jobs (2 × G.1X workers each), which is roughly US$0.10–0.20. S3, Step Functions, SNS and Athena costs are negligible at this data size. To remove everything, delete the following:
- the state machine
- the 4 Glue jobs
- the Glue databases `carevista_gold` and `carevista_ops`
- the Athena workgroup `carevista`
- the SNS topic
- the 3 `carevista-919315337648-*` buckets, after emptying them
- the roles `carevista-glue-role` and `carevista-sfn-role`
- the user `carevista-deployer` (delete its access key first)
