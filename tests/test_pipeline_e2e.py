"""End-to-end tests on the real supplied data.

The pipeline output is checked against:
  * known facts about the data (found while profiling the files), and
  * an independent pandas implementation of the same rules (tests/oracle.py).
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from pyspark.sql import functions as F

import oracle
from conftest import SOURCE_DIR
from carevista.config import SOURCE_FILES
from carevista.io import read_delta
from carevista.pipeline import run_pipeline

ENTITIES = list(SOURCE_FILES)
GOLD_TABLES = [
    "dim_patient", "dim_service", "dim_hospital", "fct_encounter", "fct_billing_line",
    "kpi1_revenue_by_department_month", "kpi2_hospital_encounter_type", "kpi3_top10_patients",
    "kpi4_patient_category_profile", "kpi5_inpatient_length_of_stay", "kpi6_region_service_category_mix",
]
PII_COLUMNS = {"first_name", "last_name", "email", "phone"}


def t(spark, cfg, zone, name):
    df = read_delta(spark, cfg.table(zone, name))
    return df.filter(F.col("batch_id") == cfg.batch_id) if zone in ("bronze", "audit") else df


@pytest.fixture(scope="module")
def expected():
    return oracle.kpis(oracle.clean(oracle.load(SOURCE_DIR)))


@pytest.fixture(scope="module")
def expected_clean():
    return oracle.clean(oracle.load(SOURCE_DIR))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------ landing ----

def test_landing_files_are_byte_identical_copies(e2e):
    from pathlib import Path

    for f in SOURCE_FILES.values():
        landed = Path(e2e.landing_dir()) / f
        assert landed.exists()
        assert sha256(landed) == sha256(SOURCE_DIR / f)


# ------------------------------------------------------------- bronze ----

@pytest.mark.parametrize("entity, rows", [("patients", 113), ("services", 22), ("encounters", 208), ("encounter_services", 572)])
def test_bronze_keeps_every_physical_row_with_lineage(spark, e2e, entity, rows):
    df = t(spark, e2e, "bronze", entity)
    assert df.count() == rows
    assert df.filter(F.col("batch_id").isNull() | F.col("source_file").isNull() | F.col("source_row_num").isNull()).count() == 0
    assert df.select("source_row_num").distinct().count() == rows
    assert set(r[0] for r in df.select("source_file").distinct().collect()) == {SOURCE_FILES[entity]}


# ------------------------------------------------------- silver/audit ----

def test_audit_read_equals_accepted_plus_rejected(spark, e2e):
    rows = t(spark, e2e, "audit", "pipeline_audit").filter("step = 'silver'").collect()
    assert len(rows) == 4
    for r in rows:
        assert r["rows_read"] == r["rows_accepted"] + r["rows_rejected"], r


@pytest.mark.parametrize("entity, accepted, rejected", [
    ("patients", 100, 13), ("services", 20, 2), ("encounters", 194, 14), ("encounter_services", 531, 41),
])
def test_accepted_and_rejected_counts(spark, e2e, entity, accepted, rejected):
    assert t(spark, e2e, "silver", entity).count() == accepted
    assert t(spark, e2e, "quarantine", entity).count() == rejected


def test_accepted_counts_match_independent_oracle(spark, e2e, expected_clean):
    assert t(spark, e2e, "silver", "patients").count() == len(expected_clean["patients"])
    assert t(spark, e2e, "silver", "services").count() == len(expected_clean["services"])
    assert t(spark, e2e, "silver", "encounters").count() == len(expected_clean["encounters"])
    assert t(spark, e2e, "silver", "encounter_services").count() == len(expected_clean["lines"])


def test_every_quarantined_row_traces_back_to_a_bronze_row(spark, e2e):
    for entity in ENTITIES:
        q = t(spark, e2e, "quarantine", entity).select("source_file", "source_row_num")
        b = t(spark, e2e, "bronze", entity).select("source_file", "source_row_num")
        assert q.subtract(b).count() == 0
        assert t(spark, e2e, "quarantine", entity).filter(F.col("reject_reason").isNull()).count() == 0


def test_silver_and_quarantine_cover_every_bronze_row_exactly_once(spark, e2e):
    for entity in ENTITIES:
        keys = lambda z: t(spark, e2e, z, entity).select("source_row_num")  # noqa: E731
        both = keys("silver").unionAll(keys("quarantine"))
        assert both.count() == both.distinct().count() == keys("bronze").count()


@pytest.mark.parametrize("entity, key, value, reason", [
    ("encounter_services", "encounter_service_id", "ES90001", "L2_NON_POSITIVE_QUANTITY"),
    ("encounter_services", "encounter_service_id", "ES90005", "L2_NEGATIVE_UNIT_PRICE"),
    ("encounter_services", "encounter_service_id", "ES90008", "L2_DISCOUNT_OUT_OF_RANGE"),
    ("encounter_services", "encounter_service_id", "ES90011", "L4_UNKNOWN_ENCOUNTER"),
    ("encounter_services", "encounter_service_id", "ES90015", "L4_UNKNOWN_SERVICE"),
    ("encounter_services", "encounter_service_id", "ES90018", "L4_ENCOUNTER_REJECTED"),
    ("encounter_services", "encounter_service_id", "ES90028", "L4_ENCOUNTER_REJECTED"),
    ("encounters", "encounter_id", "EN9001", "E3_UNKNOWN_PATIENT"),
    ("encounters", "encounter_id", "EN9006", "E3_DISCHARGE_BEFORE_ADMIT"),
    ("encounters", "encounter_id", "EN0011", "EXACT_DUPLICATE"),
    ("services", "service_id", "SV005", "EXACT_DUPLICATE"),
    ("patients", "patient_id", "PT017", "SUPERSEDED_VERSION"),
    ("patients", "patient_id", "PT010", "EXACT_DUPLICATE"),
])
def test_known_bad_rows_are_quarantined_with_the_right_reason(spark, e2e, entity, key, value, reason):
    rows = t(spark, e2e, "quarantine", entity).filter(F.col(key) == value).collect()
    assert rows, f"{value} not in quarantine/{entity}"
    assert any(reason in r["reject_reason"] for r in rows), [r["reject_reason"] for r in rows]


def test_blank_patient_ids_are_quarantined(spark, e2e):
    rows = t(spark, e2e, "quarantine", "patients").filter("reject_reason = 'P1_BLANK_PATIENT_ID'").collect()
    assert len(rows) == 2


def test_current_patient_record_uses_latest_last_updated(spark, e2e):
    pats = {r["patient_id"]: r for r in t(spark, e2e, "silver", "patients").collect()}
    assert pats["PT017"]["patient_category"] == "Corporate"   # 2026-03-01 version wins over 2024 version
    assert pats["PT043"]["patient_category"] == "Insured"
    assert pats["PT091"]["city"] == "Noida"


def test_timestamps_keep_local_wall_clock_time(spark, e2e):
    from datetime import datetime

    enc = {r["encounter_id"]: r for r in t(spark, e2e, "silver", "encounters").collect()}
    assert enc["EN0021"]["admit_timestamp"] == datetime(2026, 5, 24, 10, 49)
    assert enc["EN0021"]["discharge_timestamp"] == datetime(2026, 6, 1, 11, 2)   # from "01/06/2026 11:02"
    assert enc["EN0096"]["admit_timestamp"] == datetime(2026, 5, 23, 8, 6)       # from "23/05/2026 08:06"
    assert dict(t(spark, e2e, "silver", "encounters").dtypes)["admit_timestamp"] == "timestamp_ntz"


def test_silver_values_are_standardised(spark, e2e):
    pat = t(spark, e2e, "silver", "patients")
    enc = t(spark, e2e, "silver", "encounters")
    svc = t(spark, e2e, "silver", "services")
    assert {r[0] for r in pat.select("patient_category").distinct().collect()} == {"SelfPay", "Insured", "Corporate"}
    assert {r[0] for r in enc.select("encounter_type").distinct().collect()} == {"Inpatient", "Outpatient", "Emergency"}
    assert {r[0] for r in enc.select("encounter_status").distinct().collect()} <= {"Completed", "Discharged", "Open", "Cancelled"}
    assert {r[0] for r in svc.select("department").distinct().collect()} == {
        "Consultation", "Laboratory", "Radiology", "Pharmacy", "Procedures", "Room & Nursing"}
    assert pat.filter(F.col("first_name") != F.trim("first_name")).count() == 0


# --------------------------------------------------------------- gold ----

@pytest.mark.parametrize("table, key", [
    ("dim_patient", "patient_id"), ("dim_service", "service_id"), ("dim_hospital", "hospital_id"),
    ("fct_encounter", "encounter_id"), ("fct_billing_line", "encounter_service_id"),
])
def test_gold_keys_are_unique(spark, e2e, table, key):
    df = t(spark, e2e, "gold", table)
    assert df.count() == df.select(key).distinct().count()
    assert df.filter(F.col(key).isNull()).count() == 0


def test_gold_star_schema_has_no_orphans(spark, e2e):
    g = lambda n: t(spark, e2e, "gold", n)  # noqa: E731
    assert g("fct_billing_line").join(g("fct_encounter"), "encounter_id", "left_anti").count() == 0
    assert g("fct_billing_line").join(g("dim_service"), "service_id", "left_anti").count() == 0
    assert g("fct_encounter").join(g("dim_patient"), "patient_id", "left_anti").count() == 0
    assert g("fct_encounter").join(g("dim_hospital"), "hospital_id", "left_anti").count() == 0
    assert g("dim_hospital").count() == 6


def test_eligibility_rule_e4(spark, e2e):
    enc = t(spark, e2e, "gold", "fct_encounter")
    assert enc.filter("is_eligible AND encounter_status NOT IN ('Completed','Discharged')").count() == 0
    assert enc.filter("NOT is_eligible AND encounter_status IN ('Completed','Discharged')").count() == 0
    assert enc.filter("is_eligible").count() == 168


def test_no_personal_data_in_gold(spark, e2e):
    pii_values = {
        v for r in t(spark, e2e, "silver", "patients").select(*PII_COLUMNS).collect() for v in r if v
    }
    for name in GOLD_TABLES:
        df = t(spark, e2e, "gold", name)
        assert not PII_COLUMNS & set(df.columns), name
        cells = {str(v) for r in df.collect() for v in r}
        assert not cells & pii_values, name


# --------------------------------------------------------------- KPIs ----

def test_kpi1_matches_oracle(spark, e2e, expected):
    got = {(r["month"], r["department"]): r["billed_revenue"] for r in t(spark, e2e, "gold", "kpi1_revenue_by_department_month").collect()}
    assert got == expected["kpi1"]


def test_kpi2_matches_oracle(spark, e2e, expected):
    got = {
        (r["hospital_id"], r["encounter_type"]): (r["eligible_encounters"], r["billed_amount"], r["average_bill"])
        for r in t(spark, e2e, "gold", "kpi2_hospital_encounter_type").collect()
    }
    assert got == expected["kpi2"]


def test_kpi3_matches_oracle(spark, e2e, expected):
    got = [tuple(r) for r in t(spark, e2e, "gold", "kpi3_top10_patients").orderBy("rank").collect()]
    assert got == expected["kpi3"]
    assert t(spark, e2e, "gold", "kpi3_top10_patients").columns == ["rank", "patient_id", "eligible_encounters", "billed_amount"]


def test_kpi4_matches_oracle(spark, e2e, expected):
    got = {
        r["patient_category"]: (r["patients"], r["eligible_encounters"], r["billed_amount"], r["average_bill"])
        for r in t(spark, e2e, "gold", "kpi4_patient_category_profile").collect()
    }
    assert got == expected["kpi4"]


def test_kpi_totals_reconcile(spark, e2e):
    """Total revenue must be the same whichever KPI you add it up from."""
    total = lambda name, col: t(spark, e2e, "gold", name).agg(F.sum(col)).first()[0]  # noqa: E731
    k1 = total("kpi1_revenue_by_department_month", "billed_revenue")
    k2 = total("kpi2_hospital_encounter_type", "billed_amount")
    k4 = total("kpi4_patient_category_profile", "billed_amount")
    k6 = total("kpi6_region_service_category_mix", "billed_revenue")
    assert k1 == k2 == k4 == k6
    assert k1 == Decimal("2537703.45")
    n2 = total("kpi2_hospital_encounter_type", "eligible_encounters")
    n4 = total("kpi4_patient_category_profile", "eligible_encounters")
    assert n2 == n4 == 168


def test_stretch_kpis_are_sensible(spark, e2e):
    los = t(spark, e2e, "gold", "kpi5_inpatient_length_of_stay").collect()
    assert len(los) == 6 and all(r["avg_length_of_stay_days"] > 0 for r in los)
    mix = t(spark, e2e, "gold", "kpi6_region_service_category_mix")
    for r in mix.groupBy("hospital_region").agg(F.sum("share_of_region_pct").alias("s")).collect():
        assert abs(r["s"] - Decimal("100")) <= Decimal("0.05")


# ---------------------------------------------------- rerun / retry ----

def _snapshot(spark, cfg):
    snap = {}
    for zone, names in [("bronze", ENTITIES), ("silver", ENTITIES), ("quarantine", ENTITIES), ("gold", GOLD_TABLES)]:
        for n in names:
            df = t(spark, cfg, zone, n)
            snap[(zone, n)] = sorted(tuple(str(v) for v in r) for r in df.collect())
    audit = t(spark, cfg, "audit", "pipeline_audit").drop("recorded_at")
    snap[("audit", "pipeline_audit")] = sorted(tuple(str(v) for v in r) for r in audit.collect())
    return snap


def test_rerun_of_same_batch_changes_nothing(spark, e2e):
    before = _snapshot(spark, e2e)
    assert run_pipeline(spark, e2e)["status"] == "Succeeded"
    after = _snapshot(spark, e2e)
    assert after.keys() == before.keys()
    for key in before:
        assert after[key] == before[key], f"{key} changed after rerun"
    # bronze still holds one copy of the batch, not two
    assert t(spark, e2e, "bronze", "patients").count() == 113


def test_failed_attempt_then_retry_gives_same_results(spark, e2e):
    before = _snapshot(spark, e2e)
    summary = run_pipeline(spark, e2e, fail_once={"silver"})
    assert summary["status"] == "Succeeded"
    silver_attempts = [(x["attempt"], x["status"]) for x in summary["tasks"] if x["task"] == "silver"]
    assert silver_attempts == [(1, "Failed"), (2, "Succeeded")]
    assert _snapshot(spark, e2e) == before
    hist = t(spark, e2e, "audit", "run_history")
    assert hist.select("run_id").distinct().count() == 3   # first run + rerun + retry run
    assert hist.filter("status = 'Failed'").count() == 1


def test_source_files_were_not_changed(e2e):
    from conftest import ROOT

    for f in SOURCE_FILES.values():
        assert sha256(SOURCE_DIR / f) == sha256(ROOT / f), f"{f} differs from the original"
