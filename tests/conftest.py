from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carevista.config import PipelineConfig  # noqa: E402
from carevista.pipeline import run_pipeline  # noqa: E402
from carevista.spark import get_spark  # noqa: E402

SOURCE_DIR = ROOT / "data" / "source"
BATCH_ID = "BTEST_20260630"


@pytest.fixture(scope="session")
def spark():
    s = get_spark("carevista-tests")
    yield s
    s.stop()


@pytest.fixture(scope="session")
def e2e(spark, tmp_path_factory):
    """Run the real pipeline once on the supplied data into a temporary lake."""
    lake = tmp_path_factory.mktemp("lake")
    cfg = PipelineConfig(input_path=str(SOURCE_DIR), batch_id=BATCH_ID, lake_root=str(lake))
    summary = run_pipeline(spark, cfg)
    assert summary["status"] == "Succeeded", summary
    return cfg
