"""Audit table: rows read, accepted and rejected for each file and step.

One row per (batch_id, step, entity). Rerunning a batch replaces that batch's
rows for the step, so the audit never double counts.
"""

from __future__ import annotations

from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import types as T

from .config import PipelineConfig
from .io import write_replace_batch

AUDIT_TABLE = "pipeline_audit"
RUN_HISTORY_TABLE = "run_history"

AUDIT_SCHEMA = T.StructType(
    [
        T.StructField("batch_id", T.StringType(), False),
        T.StructField("step", T.StringType(), False),
        T.StructField("entity", T.StringType(), False),
        T.StructField("source_file", T.StringType(), True),
        T.StructField("rows_read", T.LongType(), True),
        T.StructField("rows_accepted", T.LongType(), True),
        T.StructField("rows_rejected", T.LongType(), True),
        T.StructField("detail", T.StringType(), True),
        T.StructField("recorded_at", T.TimestampType(), False),
    ]
)

RUN_HISTORY_SCHEMA = T.StructType(
    [
        T.StructField("run_id", T.StringType(), False),
        T.StructField("batch_id", T.StringType(), False),
        T.StructField("task", T.StringType(), False),
        T.StructField("attempt", T.IntegerType(), False),
        T.StructField("status", T.StringType(), False),
        T.StructField("started_at", T.TimestampType(), False),
        T.StructField("finished_at", T.TimestampType(), False),
        T.StructField("message", T.StringType(), True),
    ]
)


def write_audit(spark: SparkSession, cfg: PipelineConfig, step: str, rows: list[dict]) -> None:
    now = datetime.now()
    records = [
        (
            cfg.batch_id,
            step,
            r["entity"],
            r.get("source_file"),
            r.get("rows_read"),
            r.get("rows_accepted"),
            r.get("rows_rejected"),
            r.get("detail"),
            now,
        )
        for r in rows
    ]
    df = spark.createDataFrame(records, AUDIT_SCHEMA)
    write_replace_batch(spark, df, cfg.table("audit", AUDIT_TABLE), cfg.batch_id, extra_where=f"step = '{step}'")


def append_run_history(spark: SparkSession, cfg: PipelineConfig, record: dict) -> None:
    """Run history is a log, so it is appended (each attempt is kept)."""
    df = spark.createDataFrame(
        [
            (
                record["run_id"],
                cfg.batch_id,
                record["task"],
                record["attempt"],
                record["status"],
                record["started_at"],
                record["finished_at"],
                record.get("message"),
            )
        ],
        RUN_HISTORY_SCHEMA,
    )
    df.write.format("delta").mode("append").save(cfg.table("audit", RUN_HISTORY_TABLE))
