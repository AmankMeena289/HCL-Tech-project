"""Task 2 - bronze: load each landed CSV as-is (all text) into a Delta table.

Nothing is cleaned here. We only add lineage columns:
  * batch_id        - the load this row came from
  * source_file     - the file name it came from
  * source_row_num  - its line number in that file (1 = first data row)
  * _corrupt_record - the raw line if it could not be split into the expected columns

Rerunning a batch replaces that batch's rows (no duplicates).
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from .audit import write_audit
from .config import SOURCE_COLUMNS, SOURCE_FILES, PipelineConfig
from .io import write_replace_batch

LINEAGE_COLUMNS = ["batch_id", "source_file", "source_row_num"]


def _check_header(spark: SparkSession, path: str, expected: list[str]) -> None:
    first_line = spark.read.text(path).first()
    if first_line is None:
        raise ValueError(f"{path} is empty.")
    header = [h.strip().lstrip("﻿") for h in first_line["value"].split(",")]
    if header != expected:
        raise ValueError(f"Unexpected header in {path}.\n  expected: {expected}\n  found:    {header}")


def read_raw_csv(spark: SparkSession, path: str, entity: str) -> DataFrame:
    columns = SOURCE_COLUMNS[entity]
    _check_header(spark, path, columns)
    schema = T.StructType(
        [T.StructField(c, T.StringType(), True) for c in columns]
        + [T.StructField("_corrupt_record", T.StringType(), True)]
    )
    return (
        spark.read.option("header", "true")
        .option("encoding", "UTF-8")
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .schema(schema)
        .csv(path)
    )


def build_bronze(spark: SparkSession, cfg: PipelineConfig, entity: str) -> DataFrame:
    file_name = SOURCE_FILES[entity]
    raw = read_raw_csv(spark, f"{cfg.landing_dir()}/{file_name}", entity)
    # A small CSV is read as one partition, in file order, so this numbering is stable.
    ordered = raw.withColumn("_read_order", F.monotonically_increasing_id())
    numbered = ordered.withColumn("source_row_num", F.row_number().over(Window.orderBy("_read_order")))
    return numbered.select(
        *SOURCE_COLUMNS[entity],
        "_corrupt_record",
        F.lit(cfg.batch_id).alias("batch_id"),
        F.lit(file_name).alias("source_file"),
        F.col("source_row_num").cast("int").alias("source_row_num"),
    )


def run(spark: SparkSession, cfg: PipelineConfig) -> list[dict]:
    results = []
    for entity, file_name in SOURCE_FILES.items():
        df = build_bronze(spark, cfg, entity).cache()
        count = df.count()
        write_replace_batch(spark, df, cfg.table("bronze", entity), cfg.batch_id)
        df.unpersist()
        results.append({"entity": entity, "source_file": file_name, "rows_read": count, "rows_accepted": count, "rows_rejected": 0})
        print(f"[bronze] {file_name}: {count} rows loaded into bronze/{entity}")
    write_audit(spark, cfg, "bronze", results)
    return results
