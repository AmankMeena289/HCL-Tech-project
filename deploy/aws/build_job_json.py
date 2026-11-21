"""Write the create-job and update-job JSON for one CareVista Glue job (used by deploy.sh)."""

import json
import sys

name, task, role_arn, artifacts, staging, lake, batch_date, out_prefix = sys.argv[1:9]

job = {
    "Role": role_arn,
    "Description": f"CareVista pipeline task: {task}",
    "Command": {"Name": "glueetl", "ScriptLocation": f"s3://{artifacts}/code/glue_job.py", "PythonVersion": "3"},
    "DefaultArguments": {
        "--task": task,
        "--code_s3_uri": f"s3://{artifacts}/code/carevista.zip",
        "--input_path": f"s3://{staging}/carevista/{batch_date}",
        "--batch_id": "B20260630",
        "--lake_root": f"s3://{lake}/carevista",
        "--run_id": "manual",
        "--fail_once": "none",
        "--datalake-formats": "delta",
        "--conf": (
            "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension "
            "--conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"
        ),
        "--TempDir": f"s3://{artifacts}/glue-temp/",
        "--enable-continuous-cloudwatch-log": "true",
        "--enable-metrics": "true",
        "--job-language": "python",
    },
    "GlueVersion": "5.0",
    "WorkerType": "G.1X",
    "NumberOfWorkers": 2,
    "MaxRetries": 0,  # Step Functions does the single retry, so it is visible in the workflow history
    "Timeout": 60,
    "ExecutionProperty": {"MaxConcurrentRuns": 1},
}

with open(f"{out_prefix}-update.json", "w") as fh:
    json.dump({"JobName": name, "JobUpdate": job}, fh, indent=2)
with open(f"{out_prefix}-create.json", "w") as fh:
    json.dump({"Name": name, **job, "Tags": {"project": "carevista"}}, fh, indent=2)
