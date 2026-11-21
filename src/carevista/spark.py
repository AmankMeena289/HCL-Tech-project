"""Create or configure the Spark session.

On Databricks a session already exists, so we only set the options we rely on.
Locally we build a session with Delta Lake enabled.
"""

from __future__ import annotations

from pyspark.sql import SparkSession

# Options the cleansing logic depends on. Setting them explicitly makes results
# identical on every runtime (local Spark, Databricks, Glue, Dataproc).
SESSION_OPTIONS = {
    # Bad dates/numbers become NULL (then quarantined) instead of failing the job.
    "spark.sql.ansi.enabled": "false",
    "spark.sql.legacy.timeParserPolicy": "CORRECTED",
    "spark.sql.session.timeZone": "Asia/Kolkata",
    # Small data: few shuffle partitions keeps local runs fast.
    "spark.sql.shuffle.partitions": "4",
}


def configure_session(spark: SparkSession) -> SparkSession:
    for key, value in SESSION_OPTIONS.items():
        try:
            spark.conf.set(key, value)
        except Exception:  # some managed runtimes lock a few options; that is fine
            pass
    return spark


def get_spark(app_name: str = "carevista") -> SparkSession:
    active = SparkSession.getActiveSession()
    if active is not None:
        return configure_session(active)

    from delta import configure_spark_with_delta_pip

    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[2]")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        # Local-only speed-ups for tiny tables (Databricks manages these itself).
        .config("spark.databricks.delta.snapshotPartitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.driver.memory", "2g")
    )
    for key, value in SESSION_OPTIONS.items():
        builder = builder.config(key, value)
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
