# Databricks notebook source
# MAGIC %md
# MAGIC # CareVista pipeline - bronze task
# MAGIC Called by the Azure Data Factory pipeline `pl_carevista_daily` (see orchestration/adf/).
# MAGIC Parameters come in as widgets: **input_path**, **batch_id**, **lake_root**.

# COMMAND ----------

dbutils.widgets.text("input_path", "abfss://staging@<storage-account>.dfs.core.windows.net/carevista/2026-06-30")
dbutils.widgets.text("batch_id", "B20260630")
dbutils.widgets.text("lake_root", "abfss://lake@<storage-account>.dfs.core.windows.net/carevista")

# COMMAND ----------

import os
import sys

# The repo is synced to Databricks (Git folder). Make src/ importable.
repo_root = os.path.abspath(os.path.join(os.getcwd(), "..", ".."))
sys.path.insert(0, os.path.join(repo_root, "src"))

from carevista import bronze
from carevista.config import PipelineConfig
from carevista.spark import configure_session

configure_session(spark)
cfg = PipelineConfig(
    input_path=dbutils.widgets.get("input_path"),
    batch_id=dbutils.widgets.get("batch_id"),
    lake_root=dbutils.widgets.get("lake_root"),
)

# COMMAND ----------

results = bronze.run(spark, cfg)
display(spark.createDataFrame([{k: str(v) for k, v in r.items()} for r in results]))

# COMMAND ----------

# Row counts go back to ADF (visible in the activity output of the run history).
import json
dbutils.notebook.exit(json.dumps({"task": "bronze", "batch_id": cfg.batch_id, "results": results}, default=str))
