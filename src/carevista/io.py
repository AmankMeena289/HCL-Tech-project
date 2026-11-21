"""Small helpers to read and write Delta tables and copy files.

Paths can be local folders, abfss:// (Azure), s3:// (AWS) or gs:// (GCP).
"""

from __future__ import annotations

import hashlib

from pyspark.sql import DataFrame, SparkSession


def table_exists(spark: SparkSession, path: str) -> bool:
    from delta.tables import DeltaTable

    try:
        return DeltaTable.isDeltaTable(spark, path)
    except Exception:
        return False


def write_overwrite(df: DataFrame, path: str, partition_by: list[str] | None = None) -> None:
    """Full overwrite. Used for silver, gold and quarantine so a rerun gives the same result."""
    writer = df.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.save(path)


def write_replace_batch(spark: SparkSession, df: DataFrame, path: str, batch_id: str, extra_where: str = "") -> None:
    """Replace only the rows of one batch (bronze and audit).

    Other batches are kept, and rerunning the same batch replaces its rows
    instead of adding a second copy.
    """
    predicate = f"batch_id = '{batch_id}'" + (f" AND {extra_where}" if extra_where else "")
    if not table_exists(spark, path):
        df.write.format("delta").mode("overwrite").partitionBy("batch_id").save(path)
        return
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", predicate)
        .save(path)
    )


def read_delta(spark: SparkSession, path: str) -> DataFrame:
    return spark.read.format("delta").load(path)


# ---------------------------------------------------------------- files ----


def _dbutils(spark: SparkSession):
    try:
        from pyspark.dbutils import DBUtils  # type: ignore

        return DBUtils(spark)
    except Exception:
        return None


def copy_file(spark: SparkSession, src: str, dst: str) -> None:
    """Byte-for-byte copy using the Hadoop file system (works for every cloud scheme)."""
    try:
        jvm = spark._jvm  # not available on Spark Connect / serverless
        conf = spark._jsc.hadoopConfiguration()
        src_path = jvm.org.apache.hadoop.fs.Path(src)
        dst_path = jvm.org.apache.hadoop.fs.Path(dst)
        src_fs = src_path.getFileSystem(conf)
        dst_fs = dst_path.getFileSystem(conf)
        if not src_fs.exists(src_path):
            raise FileNotFoundError(f"Source file not found: {src}")
        dst_fs.mkdirs(dst_path.getParent())
        jvm.org.apache.hadoop.fs.FileUtil.copy(src_fs, src_path, dst_fs, dst_path, False, True, conf)
        return
    except FileNotFoundError:
        raise
    except Exception:
        dbutils = _dbutils(spark)
        if dbutils is None:
            raise
        dbutils.fs.cp(src, dst)


def file_digest(spark: SparkSession, path: str) -> tuple[int, str]:
    """Return (size in bytes, sha256) of a file, read through Spark so any storage works."""
    row = spark.read.format("binaryFile").load(path).select("content").first()
    if row is None:
        raise FileNotFoundError(path)
    content = bytes(row["content"])
    return len(content), hashlib.sha256(content).hexdigest()
