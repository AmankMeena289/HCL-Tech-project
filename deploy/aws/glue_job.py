"""AWS Glue entry point for one CareVista pipeline task.

The same script backs four Glue jobs (carevista-01-landing ... carevista-04-gold).
Each job has a default --task argument; Step Functions passes the run
parameters (--input_path, --batch_id, --lake_root, --run_id).

The carevista package is shipped as a zip on S3 (--code_s3_uri). It is
downloaded and unpacked to local disk instead of being imported straight from
the zip, because gold.py reads its KPI .sql files from the package folder.

Every attempt is written to audit/run_history, like the local runner does.
Step Functions retries a failed task once; the attempt number is derived from
the rows already in run_history for this run_id and task.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import zipfile
from datetime import datetime

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

ARG_NAMES = ["JOB_NAME", "task", "input_path", "batch_id", "lake_root", "code_s3_uri", "run_id", "fail_once"]
args = getResolvedOptions(sys.argv, ARG_NAMES)


def load_package(code_s3_uri: str) -> None:
    bucket, key = code_s3_uri.replace("s3://", "", 1).split("/", 1)
    local_zip = "/tmp/carevista_code.zip"
    target = "/tmp/carevista_code"
    boto3.client("s3").download_file(bucket, key, local_zip)
    with zipfile.ZipFile(local_zip) as zf:
        zf.extractall(target)
    sys.path.insert(0, target)


load_package(args["code_s3_uri"])

from carevista import bronze, gold, landing, silver  # noqa: E402
from carevista.audit import RUN_HISTORY_TABLE, append_run_history  # noqa: E402
from carevista.config import PipelineConfig  # noqa: E402
from carevista.io import read_delta, table_exists  # noqa: E402
from carevista.spark import configure_session  # noqa: E402

TASKS = {"landing": landing.run, "bronze": bronze.run, "silver": silver.run, "gold": gold.run}

sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)
spark = configure_session(glue_context.spark_session)
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

task = args["task"]
if task not in TASKS:
    raise ValueError(f"Unknown task {task!r}; expected one of {sorted(TASKS)}")

cfg = PipelineConfig(input_path=args["input_path"], batch_id=args["batch_id"], lake_root=args["lake_root"])
run_id = args["run_id"]


def next_attempt() -> int:
    path = cfg.table("audit", RUN_HISTORY_TABLE)
    if not table_exists(spark, path):
        return 1
    done = read_delta(spark, path).where(f"run_id = '{run_id}' AND task = '{task}'").count()
    return done + 1


attempt = next_attempt()
started = datetime.now()
print(f"=== run_id={run_id} task={task} attempt={attempt} batch_id={cfg.batch_id} ===")

error: Exception | None = None
results = None
try:
    # Optional demo of a failed attempt followed by a successful retry.
    if args["fail_once"] == task and attempt == 1:
        raise RuntimeError(f"Injected failure in task '{task}' (attempt {attempt})")
    results = TASKS[task](spark, cfg)
    status, message = "Succeeded", None
except Exception as exc:  # noqa: BLE001 - logged, then re-raised so Step Functions retries
    traceback.print_exc()
    error = exc
    status, message = "Failed", f"{type(exc).__name__}: {exc}"[:2000]

append_run_history(
    spark,
    cfg,
    {
        "run_id": run_id,
        "task": task,
        "attempt": attempt,
        "status": status,
        "started_at": started,
        "finished_at": datetime.now(),
        "message": message,
    },
)
print(f"--- task={task} attempt={attempt} status={status}" + (f" ({message})" if message else ""))

if error is not None:
    raise error

# After gold, also publish the CSV/Markdown/HTML KPI report next to the lake.
if task == "gold":
    from carevista.report import write_report

    report_dir = "/tmp/carevista_report"
    write_report(spark, cfg, report_dir)
    bucket, prefix = cfg.lake_root.replace("s3://", "", 1).split("/", 1)
    s3 = boto3.client("s3")
    for name in os.listdir(report_dir):
        s3.upload_file(os.path.join(report_dir, name), bucket, f"{prefix.rstrip('/')}/reports/{name}")
    print(f"[report] uploaded to s3://{bucket}/{prefix.rstrip('/')}/reports/")

print(json.dumps({"task": task, "batch_id": cfg.batch_id, "results": results}, default=str)[:4000])
job.commit()
