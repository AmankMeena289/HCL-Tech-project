# CareVista results dashboard (localhost)

A local web page that shows the result of the CareVista pipeline run on AWS: pipeline progress, evaluation checks, rows accepted and rejected per file, a graph for each of the six KPIs, and the AWS resources in use.

It is plain HTML, CSS and JavaScript with no libraries and no internet needed. Python's built-in web server serves it.

## Show it

```powershell
# Windows PowerShell, from the project folder
.\scripts\start_frontend.ps1             # opens http://localhost:8000
```

```bash
# Git Bash / WSL / macOS / Linux
./scripts/start_frontend.sh              # then open http://localhost:8000
```

The page reads `frontend/data/results.json`. It is already exported, so the demo works offline.

## Refresh the results from AWS

You need an AWS login first (`aws login`, then check with `aws sts get-caller-identity`).

```powershell
.\scripts\start_frontend.ps1 -Refresh    # export from AWS, then serve
# or only export:
python deploy/aws/export_results.py
```

The export only reads from AWS:

| What | Where it comes from |
|---|---|
| Pipeline steps, status, attempts, time | Step Functions execution history (`carevista-daily`, newest run not stopped by hand; set `EXECUTION_NAME` to choose one) |
| Rows read / accepted / rejected | Athena query on `carevista_ops.pipeline_audit` (silver step) |
| KPI 1–6 | CSVs the gold step publishes to `s3://<lake>/carevista/reports/` |
| AWS resources | `head-bucket`, `get-job`, `describe-state-machine`, … one read per resource |

## Full order on a fresh account

```bash
AWS_PROFILE=default AWS_REGION=ap-southeast-2 bash deploy/aws/deploy.sh
AWS_PROFILE=default bash deploy/aws/run_pipeline.sh B20260630
AWS_PROFILE=default bash deploy/aws/athena_register.sh
python deploy/aws/export_results.py
./scripts/start_frontend.sh
```

This account's organization blocks Glue and Step Functions in `ap-south-1` (Mumbai), so the stack runs in `ap-southeast-2` (Sydney).
