"""Collect the results of the latest CareVista run on AWS into frontend/data/.

Writes
  frontend/data/results.json   everything the local dashboard shows
  frontend/data/csv/*.csv      the KPI CSVs and HTML/Markdown report published by the gold step

Run after deploy.sh, run_pipeline.sh and athena_register.sh:

  python deploy/aws/export_results.py            # uses AWS_PROFILE if set, else the default profile

Only the AWS CLI is needed (no boto3). Every call only reads.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "frontend" / "data"
BATCH_ID = os.environ.get("BATCH_ID", "B20260630")
EXPECTED_REVENUE = 2537703.45  # local run, README "Results"
EXPECTED_ENCOUNTERS = 168

TASKS = [("01_Landing", "landing"), ("02_Bronze", "bronze"), ("03_Silver", "silver"), ("04_Gold", "gold")]
KPIS = [
    "kpi1_revenue_by_department_month",
    "kpi2_hospital_encounter_type",
    "kpi3_top10_patients",
    "kpi4_patient_category_profile",
    "kpi5_inpatient_length_of_stay",
    "kpi6_region_service_category_mix",
]


def load_outputs() -> dict:
    path = HERE / "build" / "outputs.env"
    if not path.exists():
        sys.exit("deploy/aws/build/outputs.env not found: run deploy.sh first.")
    vals = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            vals[key.strip()] = value.strip()
    return vals


ENV = load_outputs()
REGION = ENV["REGION"]


def aws(*args: str, parse: bool = True):
    cmd = ["aws", *args, "--region", REGION, "--output", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args[:2])} failed: {res.stderr.strip()}")
    if parse:
        return json.loads(res.stdout) if res.stdout.strip() else {}
    return res.stdout


def iso(ts) -> str | None:
    return ts if ts is None else str(ts)


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


# ------------------------------------------------------------------ pipeline ----
def pipeline() -> dict:
    # Newest run first. Runs stopped by hand (ABORTED) are skipped; set EXECUTION_NAME to pick one run.
    execs = aws("stepfunctions", "list-executions", "--state-machine-arn", ENV["SM_ARN"], "--max-results", "50").get("executions", [])
    wanted = os.environ.get("EXECUTION_NAME")
    if wanted:
        execs = [e for e in execs if e["name"] == wanted]
    else:
        execs = [e for e in execs if e["status"] != "ABORTED"] or execs
    if not execs:
        return {"execution": None, "steps": []}
    arn = execs[0]["executionArn"]
    desc = aws("stepfunctions", "describe-execution", "--execution-arn", arn)
    events = aws("stepfunctions", "get-execution-history", "--execution-arn", arn, "--max-items", "1000")["events"]

    steps = {task: {"state": state, "task": task, "status": "NOT STARTED", "attempts": 0, "started_at": None,
                    "finished_at": None, "duration_s": None, "glue_seconds": None, "glue_job_run_id": None, "error": None}
             for state, task in TASKS}
    by_state = {state: task for state, task in TASKS}
    current = None
    for ev in events:
        etype = ev["type"]
        if etype == "TaskStateEntered":
            current = by_state.get(ev["stateEnteredEventDetails"]["name"])
            if current:
                steps[current]["status"] = "RUNNING"
                steps[current]["started_at"] = iso(ev["timestamp"])
        elif current and etype == "TaskScheduled":
            steps[current]["attempts"] += 1
        elif current and etype == "TaskSucceeded":
            out = json.loads(ev["taskSucceededEventDetails"].get("output") or "{}")
            steps[current]["status"] = "SUCCEEDED"
            steps[current]["glue_seconds"] = out.get("ExecutionTime")
            steps[current]["glue_job_run_id"] = out.get("Id")
            steps[current]["error"] = None
        elif current and etype in ("TaskFailed", "TaskTimedOut"):
            details = ev.get("taskFailedEventDetails") or ev.get("taskTimedOutEventDetails") or {}
            steps[current]["status"] = "FAILED"
            steps[current]["error"] = (details.get("error") or "") + (": " + details["cause"][:300] if details.get("cause") else "")
        elif current and etype == "TaskStateExited":
            steps[current]["finished_at"] = iso(ev["timestamp"])
            s = steps[current]
            if s["started_at"]:
                s["duration_s"] = round((parse_ts(s["finished_at"]) - parse_ts(s["started_at"])).total_seconds())
            current = None

    region = REGION
    return {
        "execution": {
            "name": desc["name"],
            "status": desc["status"],
            "started_at": iso(desc.get("startDate")),
            "finished_at": iso(desc.get("stopDate")),
            "input": json.loads(desc.get("input") or "{}"),
            "console_url": f"https://{region}.console.aws.amazon.com/states/home?region={region}#/v2/executions/details/{arn}",
        },
        "steps": [steps[task] for _, task in TASKS],
    }


# ------------------------------------------------------------------ athena ----
def athena(sql: str) -> list[dict]:
    qid = aws("athena", "start-query-execution", "--work-group", "carevista", "--query-string", sql)["QueryExecutionId"]
    while True:
        status = aws("athena", "get-query-execution", "--query-execution-id", qid)["QueryExecution"]["Status"]
        if status["State"] in ("QUEUED", "RUNNING"):
            time.sleep(1.5)
            continue
        if status["State"] != "SUCCEEDED":
            raise RuntimeError(status.get("StateChangeReason", status["State"]))
        break
    rows = aws("athena", "get-query-results", "--query-execution-id", qid)["ResultSet"]["Rows"]
    header = [c.get("VarCharValue") for c in rows[0]["Data"]]
    return [dict(zip(header, [c.get("VarCharValue") for c in r["Data"]])) for r in rows[1:]]


def audit() -> tuple[list[dict], str | None]:
    try:
        rows = athena(
            "SELECT source_file, rows_read, rows_accepted, rows_rejected FROM carevista_ops.pipeline_audit "
            f"WHERE batch_id = '{BATCH_ID}' AND step = 'silver' ORDER BY source_file"
        )
    except RuntimeError as exc:
        return [], f"Audit table could not be read from Athena ({exc}). Run deploy/aws/athena_register.sh first."
    return [{k: (int(v) if k.startswith("rows_") and v is not None else v) for k, v in r.items()} for r in rows], None


def run_history(run_id: str) -> list[dict]:
    try:
        return athena(
            "SELECT task, attempt, status, CAST(started_at AS varchar) AS started_at, CAST(finished_at AS varchar) AS finished_at, message "
            f"FROM carevista_ops.run_history WHERE run_id = '{run_id}' ORDER BY started_at"
        )
    except RuntimeError:
        return []


# ------------------------------------------------------------------ kpis ----
def kpis() -> dict:
    csv_dir = OUT / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    aws("s3", "cp", f"s3://{ENV['LAKE']}/carevista/reports/", str(csv_dir), "--recursive", "--only-show-errors", parse=False)
    result = {}
    for name in KPIS:
        path = csv_dir / f"{name}.csv"
        result[name] = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    return result


# ------------------------------------------------------------------ resources ----
def resources() -> list[dict]:
    acct = ENV["ACCOUNT"]
    checks = [
        ("Amazon S3", ENV["STAGING"], "Staging area: the four source CSVs, unchanged", ("s3api", "head-bucket", "--bucket", ENV["STAGING"])),
        ("Amazon S3", ENV["LAKE"], "Data lake: landing, bronze, silver, gold, quarantine and audit (Delta Lake)", ("s3api", "head-bucket", "--bucket", ENV["LAKE"])),
        ("Amazon S3", ENV["ARTIFACTS"], "Pipeline code, Glue temp files and Athena results", ("s3api", "head-bucket", "--bucket", ENV["ARTIFACTS"])),
    ]
    for i, (_, task) in enumerate(TASKS, 1):
        name = f"carevista-0{i}-{task}"
        checks.append(("AWS Glue", name, f"PySpark job for the {task} step", ("glue", "get-job", "--job-name", name)))
    checks += [
        ("AWS Step Functions", "carevista-daily", "Runs the four Glue jobs in order, one retry each, alert on failure",
         ("stepfunctions", "describe-state-machine", "--state-machine-arn", ENV["SM_ARN"])),
        ("Amazon SNS", "carevista-pipeline-alerts", "Failure alert topic", ("sns", "get-topic-attributes", "--topic-arn", ENV["TOPIC_ARN"])),
        ("Amazon Athena", "carevista", "Workgroup for SQL on the gold and audit tables", ("athena", "get-work-group", "--work-group", "carevista")),
        ("AWS Glue Data Catalog", "carevista_gold", "Star schema and KPI tables", ("glue", "get-database", "--name", "carevista_gold")),
        ("AWS Glue Data Catalog", "carevista_ops", "Audit and run history tables", ("glue", "get-database", "--name", "carevista_ops")),
        ("AWS IAM", "carevista-glue-role", "Role the Glue jobs run as (only the CareVista buckets)", ("iam", "get-role", "--role-name", "carevista-glue-role")),
        ("AWS IAM", "carevista-sfn-role", "Role the workflow runs as (start Glue jobs, publish alert)", ("iam", "get-role", "--role-name", "carevista-sfn-role")),
    ]
    out = []
    for service, name, purpose, call in checks:
        try:
            aws(*call)
            status = "Active"
        except RuntimeError:
            status = "Missing"
        out.append({"service": service, "name": name, "purpose": purpose, "status": status})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Account {ENV['ACCOUNT']}, region {REGION}")
    pipe = pipeline()
    print(f"pipeline: {pipe['execution']['status'] if pipe['execution'] else 'no runs yet'}")
    audit_rows, audit_warning = audit()
    print(f"audit rows: {len(audit_rows)}" + (f" ({audit_warning})" if audit_warning else ""))
    history = run_history(pipe["execution"]["name"]) if pipe["execution"] else []
    kpi = kpis()
    print("kpis: " + ", ".join(f"{k.split('_')[0]}={len(v)}" for k, v in kpi.items()))
    res = resources()
    print(f"resources: {sum(r['status'] == 'Active' for r in res)}/{len(res)} active")

    data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "account": ENV["ACCOUNT"],
            "region": REGION,
            "batch_id": BATCH_ID,
            "cutoff": "2026-06-30 23:59:59",
            "lake": f"s3://{ENV['LAKE']}/carevista",
            "expected": {"billed_revenue": EXPECTED_REVENUE, "eligible_encounters": EXPECTED_ENCOUNTERS},
        },
        "pipeline": pipe,
        "run_history": history,
        "audit": audit_rows,
        "warnings": [w for w in [audit_warning] if w],
        "kpis": kpi,
        "resources": res,
    }
    (OUT / "results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"written {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
