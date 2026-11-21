"""Local workflow runner: landing -> bronze -> silver -> gold, in order.

This mirrors the cloud workflow (Azure Data Factory pipeline in
orchestration/adf/): same four tasks, same parameters (input_path, batch_id),
one retry per task. Every attempt is written to audit/run_history.

Usage:
    python -m carevista.pipeline --input-path <folder> --batch-id B20260630 --lake-root ./lake
    # optional: make one task fail once to show the retry working
    python -m carevista.pipeline ... --fail-once silver
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime
from typing import Callable

from pyspark.sql import SparkSession

from . import bronze, gold, landing, silver
from .audit import append_run_history
from .config import PipelineConfig
from .spark import get_spark

TASKS: list[tuple[str, Callable]] = [
    ("landing", landing.run),
    ("bronze", bronze.run),
    ("silver", silver.run),
    ("gold", gold.run),
]
RETRIES_PER_TASK = 1


class InjectedFailure(RuntimeError):
    """Raised on purpose (--fail-once) to demonstrate a failed attempt and a retry."""


def run_pipeline(
    spark: SparkSession,
    cfg: PipelineConfig,
    retries: int = RETRIES_PER_TASK,
    fail_once: set[str] | None = None,
    tasks: list[tuple[str, Callable]] | None = None,
) -> dict:
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    pending_failures = set(fail_once or ())
    summary = {"run_id": run_id, "batch_id": cfg.batch_id, "tasks": []}
    print(f"=== Run {run_id} | batch_id={cfg.batch_id} | input_path={cfg.input_path} ===")

    for task_name, task_fn in tasks or TASKS:
        for attempt in range(1, retries + 2):
            started = datetime.now()
            try:
                if task_name in pending_failures:
                    pending_failures.discard(task_name)
                    raise InjectedFailure(f"Injected failure in task '{task_name}' (attempt {attempt})")
                task_fn(spark, cfg)
                status, message = "Succeeded", None
            except Exception as exc:  # noqa: BLE001 - we log and retry any task error
                status, message = "Failed", f"{type(exc).__name__}: {exc}"[:2000]
            append_run_history(
                spark,
                cfg,
                {
                    "run_id": run_id,
                    "task": task_name,
                    "attempt": attempt,
                    "status": status,
                    "started_at": started,
                    "finished_at": datetime.now(),
                    "message": message,
                },
            )
            summary["tasks"].append({"task": task_name, "attempt": attempt, "status": status, "message": message})
            print(f"--- task={task_name} attempt={attempt} status={status}" + (f" ({message})" if message else ""))
            if status == "Succeeded":
                break
        else:
            summary["status"] = "Failed"
            print(f"=== Run {run_id} FAILED at task '{task_name}' after {retries + 1} attempts ===")
            return summary

    summary["status"] = "Succeeded"
    print(f"=== Run {run_id} SUCCEEDED ===")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the CareVista pipeline locally.")
    parser.add_argument("--input-path", required=True, help="Folder holding the four source CSV files")
    parser.add_argument("--batch-id", required=True, help="Batch label, e.g. B20260630")
    parser.add_argument("--lake-root", default="./lake", help="Base folder for the lake zones")
    parser.add_argument("--fail-once", action="append", default=[], help="Task to fail once (demo of retry)")
    parser.add_argument("--report-dir", default=None, help="If set, write KPI CSV/Markdown/HTML report here")
    args = parser.parse_args(argv)

    cfg = PipelineConfig(input_path=args.input_path, batch_id=args.batch_id, lake_root=args.lake_root)
    spark = get_spark()
    summary = run_pipeline(spark, cfg, fail_once=set(args.fail_once))
    if summary["status"] == "Succeeded" and args.report_dir:
        from .report import write_report

        write_report(spark, cfg, args.report_dir)
    return 0 if summary["status"] == "Succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
