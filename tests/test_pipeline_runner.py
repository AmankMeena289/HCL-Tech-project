"""Workflow runner: order of tasks, one retry per task, stop on failure, parameters."""

from __future__ import annotations

import pytest
from pyspark.sql import functions as F

from carevista.bronze import read_raw_csv
from carevista.config import PipelineConfig
from carevista.io import read_delta
from carevista.pipeline import run_pipeline


def _cfg(tmp_path, batch="B1"):
    return PipelineConfig(input_path=str(tmp_path / "in"), batch_id=batch, lake_root=str(tmp_path / "lake"))


def test_tasks_run_in_order(spark, tmp_path):
    calls = []
    tasks = [(n, lambda s, c, n=n: calls.append(n)) for n in ("landing", "bronze", "silver", "gold")]
    summary = run_pipeline(spark, _cfg(tmp_path), tasks=tasks)
    assert summary["status"] == "Succeeded"
    assert calls == ["landing", "bronze", "silver", "gold"]


def test_a_failed_task_is_retried_once_then_the_run_continues(spark, tmp_path):
    calls = []
    tasks = [(n, lambda s, c, n=n: calls.append(n)) for n in ("landing", "bronze", "silver", "gold")]
    cfg = _cfg(tmp_path)
    summary = run_pipeline(spark, cfg, tasks=tasks, fail_once={"silver"})
    assert summary["status"] == "Succeeded"
    attempts = [(t["task"], t["attempt"], t["status"]) for t in summary["tasks"]]
    assert ("silver", 1, "Failed") in attempts and ("silver", 2, "Succeeded") in attempts
    hist = read_delta(spark, cfg.table("audit", "run_history")).filter(F.col("task") == "silver")
    assert hist.count() == 2


def test_a_task_failing_twice_stops_the_run(spark, tmp_path):
    calls = []

    def broken(s, c):
        raise ValueError("boom")

    tasks = [("landing", lambda s, c: calls.append("landing")), ("bronze", broken), ("silver", lambda s, c: calls.append("silver"))]
    summary = run_pipeline(spark, _cfg(tmp_path), tasks=tasks)
    assert summary["status"] == "Failed"
    assert calls == ["landing"]  # silver never ran
    assert [t["status"] for t in summary["tasks"] if t["task"] == "bronze"] == ["Failed", "Failed"]


@pytest.mark.parametrize("bad", ["", "has space", "x" * 65, "semi;colon", "quote'"])
def test_batch_id_is_validated(tmp_path, bad):
    with pytest.raises(ValueError):
        PipelineConfig(input_path="in", batch_id=bad, lake_root="lake")


def test_paths_follow_zone_layout():
    cfg = PipelineConfig(input_path="in", batch_id="B1", lake_root="abfss://lake@acct.dfs.core.windows.net/carevista/")
    assert cfg.table("silver", "patients") == "abfss://lake@acct.dfs.core.windows.net/carevista/silver/patients"
    assert cfg.landing_dir().endswith("/landing/batch_id=B1")
    with pytest.raises(ValueError):
        cfg.zone("temp")


def test_unexpected_header_fails_fast(spark, tmp_path):
    p = tmp_path / "services.csv"
    p.write_text("service_id,name,service_category,department\nSV001,X,Consultation,Consultation\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected header"):
        read_raw_csv(spark, str(p), "services")


def test_row_with_extra_columns_is_marked_corrupt(spark, tmp_path):
    p = tmp_path / "services.csv"
    p.write_text(
        "service_id,service_name,service_category,department\n"
        "SV001,General Consultation,Consultation,Consultation\n"
        "SV002,Specialist,Consultation,Consultation,EXTRA\n",
        encoding="utf-8",
    )
    rows = read_raw_csv(spark, str(p), "services").collect()
    assert rows[0]["_corrupt_record"] is None
    assert rows[1]["_corrupt_record"] == "SV002,Specialist,Consultation,Consultation,EXTRA"
