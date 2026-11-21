"""Silver cleansing rules tested on small hand-made inputs (one rule per test)."""

from __future__ import annotations

from decimal import Decimal

from carevista import silver
from carevista.config import SOURCE_COLUMNS

CUTOFF = "2026-06-30 23:59:59"


def bronze_df(spark, entity, rows):
    cols = SOURCE_COLUMNS[entity]
    data = [
        tuple(r.get(c) for c in cols) + (r.get("_corrupt_record"), "B1", f"{entity}.csv", i + 1)
        for i, r in enumerate(rows)
    ]
    schema = ", ".join(f"{c} string" for c in cols) + ", _corrupt_record string, batch_id string, source_file string, source_row_num int"
    return spark.createDataFrame(data, schema)


def patient(pid, cat="Insured", lu="2025-01-01 09:00:00", city="Pune", **kw):
    base = dict(patient_id=pid, first_name="A", last_name="B", email="a@example.com", phone="1",
                date_of_birth="1990-01-01", gender="Male", city=city, patient_category=cat,
                registration_date="2024-01-01", last_updated=lu)
    base.update(kw)
    return base


def encounter(eid, pid="PT001", status="Completed", admit="2026-03-01 10:00:00", discharge="2026-03-01 12:00:00", etype="Outpatient"):
    return dict(encounter_id=eid, patient_id=pid, hospital_id="H01", hospital_name="CareVista Delhi Central",
                hospital_city="Delhi", hospital_region="North", encounter_type=etype,
                admit_timestamp=admit, discharge_timestamp=discharge, encounter_status=status)


def line(lid, eid="EN0001", sid="SV001", sdate="2026-03-01", qty="1", price="100.00", disc="0"):
    return dict(encounter_service_id=lid, encounter_id=eid, service_id=sid, service_date=sdate,
                quantity=qty, unit_price=price, discount_pct=disc)


def reasons(result, key):
    return {r[key]: r["reject_reason"] for r in result.rejected.collect()}


def accepted(result, key):
    return {r[key]: r for r in result.accepted.collect()}


# ---------------------------------------------------------------- patients --

def test_patients_latest_last_updated_wins_and_old_version_is_quarantined(spark):
    df = bronze_df(spark, "patients", [
        patient("PT017", cat="Insured", lu="2024-02-04 09:00:00", city="Delhi"),
        patient("PT017", cat="corporate", lu="2026-03-01 11:11:00", city="Chandigarh"),
    ])
    res = silver.clean_patients(df)
    ok = accepted(res, "patient_id")
    assert ok["PT017"]["patient_category"] == "Corporate"
    assert ok["PT017"]["city"] == "Chandigarh"
    assert list(reasons(res, "patient_id").values()) == ["SUPERSEDED_VERSION"]


def test_patients_exact_duplicate_is_flagged_as_exact(spark):
    df = bronze_df(spark, "patients", [patient("PT010"), patient("PT010")])
    res = silver.clean_patients(df)
    assert res.accepted.count() == 1
    assert [r["reject_reason"] for r in res.rejected.collect()] == ["EXACT_DUPLICATE"]
    # the first row in the file is the one kept
    assert res.accepted.first()["source_row_num"] == 1


def test_patients_blank_id_and_bad_category_are_rejected(spark):
    df = bronze_df(spark, "patients", [patient(None), patient("   "), patient("PT002", cat="Gold"), patient("PT003")])
    res = silver.clean_patients(df)
    assert set(accepted(res, "patient_id")) == {"PT003"}
    got = sorted(r["reject_reason"] for r in res.rejected.collect())
    assert got == ["P1_BLANK_PATIENT_ID", "P1_BLANK_PATIENT_ID", "P2_INVALID_PATIENT_CATEGORY"]


def test_patients_names_are_trimmed(spark):
    res = silver.clean_patients(bronze_df(spark, "patients", [patient("PT001", first_name="  Diya")]))
    assert res.accepted.first()["first_name"] == "Diya"


def test_quarantine_keeps_original_text(spark):
    df = bronze_df(spark, "patients", [patient("PT002", cat="Gold", first_name="  Riya")])
    rej = silver.clean_patients(df).rejected.first()
    assert rej["patient_category"] == "Gold" and rej["first_name"] == "  Riya"
    assert rej["source_file"] == "patients.csv" and rej["source_row_num"] == 1 and rej["batch_id"] == "B1"


# ---------------------------------------------------------------- services --

def test_services_department_standardised_and_duplicates_removed(spark):
    df = bronze_df(spark, "services", [
        dict(service_id="SV010", service_name="Ultrasound Abdomen", service_category="Diagnostic", department="radiology"),
        dict(service_id="SV010", service_name="Ultrasound Abdomen", service_category="Diagnostic", department="radiology"),
        dict(service_id="SV012", service_name="IV Fluids", service_category="Medication", department="pharmacy"),
    ])
    res = silver.clean_services(df)
    ok = accepted(res, "service_id")
    assert ok["SV010"]["department"] == "Radiology" and ok["SV012"]["department"] == "Pharmacy"
    assert [r["reject_reason"] for r in res.rejected.collect()] == ["EXACT_DUPLICATE"]


def test_malformed_row_is_rejected(spark):
    df = bronze_df(spark, "services", [
        dict(service_id="SV001", service_name="X", service_category="Consultation", department="Consultation",
             _corrupt_record="SV001,X,Consultation,Consultation,EXTRA"),
    ])
    res = silver.clean_services(df)
    assert res.accepted.count() == 0
    assert res.rejected.first()["reject_reason"] == "MALFORMED_ROW"


# -------------------------------------------------------------- encounters --

def _patients(spark, *ids):
    return spark.createDataFrame([(i,) for i in ids], "patient_id string")


def test_encounters_reject_unknown_patient_bad_dates_and_after_cutoff(spark):
    df = bronze_df(spark, "encounters", [
        encounter("EN0001"),
        encounter("EN9001", pid="PT901"),
        encounter("EN9006", admit="09/04/2026 11:52", discharge="2026-04-07 11:52:00", status="Discharged"),
        encounter("EN0002", admit="2026-07-01 10:00:00", discharge="2026-07-01 11:00:00"),
        encounter("EN0003", etype="Daycare"),
        encounter("EN0004", admit="not a date"),
    ])
    res = silver.clean_encounters(df, _patients(spark, "PT001"), CUTOFF)
    assert set(accepted(res, "encounter_id")) == {"EN0001"}
    got = reasons(res, "encounter_id")
    assert got["EN9001"] == "E3_UNKNOWN_PATIENT"
    assert got["EN9006"] == "E3_DISCHARGE_BEFORE_ADMIT"
    assert got["EN0002"] == "E3_ADMIT_AFTER_CUTOFF"
    assert got["EN0003"] == "E2_INVALID_ENCOUNTER_TYPE"
    assert got["EN0004"] == "E2_INVALID_ADMIT_TIMESTAMP"


def test_encounters_standardise_type_and_status_and_keep_open_with_blank_discharge(spark):
    df = bronze_df(spark, "encounters", [
        encounter("EN0001", etype="OUTPATIENT", status="completed"),
        encounter("EN0002", etype="inpatient", status="open", discharge=None),
    ])
    ok = accepted(silver.clean_encounters(df, _patients(spark, "PT001"), CUTOFF), "encounter_id")
    assert (ok["EN0001"]["encounter_type"], ok["EN0001"]["encounter_status"]) == ("Outpatient", "Completed")
    assert (ok["EN0002"]["encounter_type"], ok["EN0002"]["encounter_status"]) == ("Inpatient", "Open")
    assert ok["EN0002"]["discharge_timestamp"] is None


# ------------------------------------------------------------------- lines --

def _clean_lines(spark, rows, encounters=None, bronze_ids=("EN0001", "EN9006"), services=("SV001",)):
    enc_rows = encounters or [("EN0001", "2026-03-01 10:00:00", "2026-03-02 12:00:00")]
    enc = spark.createDataFrame(enc_rows, "encounter_id string, a string, d string").selectExpr(
        "encounter_id", "to_timestamp(a) AS admit_timestamp", "to_timestamp(d) AS discharge_timestamp"
    )
    ids = spark.createDataFrame([(i,) for i in bronze_ids], "encounter_id string")
    svc = spark.createDataFrame([(s,) for s in services], "service_id string")
    return silver.clean_encounter_services(bronze_df(spark, "encounter_services", rows), enc, ids, svc, CUTOFF)


def test_lines_each_bad_value_has_its_own_reason(spark):
    res = _clean_lines(spark, [
        line("ES1"),
        line("ES2", qty="-1"),
        line("ES3", price="-500.00"),
        line("ES4", disc="120"),
        line("ES5", sid="SV999"),
        line("ES6", eid="EN8001"),
        line("ES7", eid="EN9006"),
        line("ES8", sdate="2026-02-28"),
        line("ES9", sdate="2026-03-05"),
        line("ES10", price="abc"),
        line("ES11", sdate="2026-07-01"),
    ])
    assert set(accepted(res, "encounter_service_id")) == {"ES1"}
    got = reasons(res, "encounter_service_id")
    assert got["ES2"] == "L2_NON_POSITIVE_QUANTITY"
    assert got["ES3"] == "L2_NEGATIVE_UNIT_PRICE"
    assert got["ES4"] == "L2_DISCOUNT_OUT_OF_RANGE"
    assert got["ES5"] == "L4_UNKNOWN_SERVICE"
    assert got["ES6"] == "L4_UNKNOWN_ENCOUNTER"
    assert got["ES7"] == "L4_ENCOUNTER_REJECTED"
    assert got["ES8"] == "L4_SERVICE_BEFORE_ADMIT"
    assert got["ES9"] == "L4_SERVICE_AFTER_DISCHARGE"
    assert got["ES10"] == "L2_INVALID_UNIT_PRICE"
    assert "L2_SERVICE_AFTER_CUTOFF" in got["ES11"]


def test_lines_several_problems_are_all_listed(spark):
    res = _clean_lines(spark, [line("ES1", qty="-1", sid="SV999")])
    assert res.rejected.first()["reject_reason"] == "L2_NON_POSITIVE_QUANTITY; L4_UNKNOWN_SERVICE"


def test_lines_currency_text_blank_discount_and_line_charge(spark):
    res = _clean_lines(spark, [
        line("ES1", qty="2", price="Rs. 1,000", disc=""),
        line("ES2", qty="3", price="₹333.33", disc="10"),
    ])
    ok = accepted(res, "encounter_service_id")
    assert ok["ES1"]["unit_price"] == Decimal("1000.00") and ok["ES1"]["discount_pct"] == Decimal("0.00")
    assert ok["ES1"]["line_charge"] == Decimal("2000.00")
    assert ok["ES2"]["line_charge"] == Decimal("899.99")


def test_lines_duplicate_line_id_kept_once(spark):
    res = _clean_lines(spark, [line("ES1"), line("ES1")])
    assert res.accepted.count() == 1
    assert [r["reject_reason"] for r in res.rejected.collect()] == ["EXACT_DUPLICATE"]


def test_lines_same_id_with_different_values_is_a_key_conflict(spark):
    res = _clean_lines(spark, [line("ES1", price="100.00"), line("ES1", price="200.00")])
    assert accepted(res, "encounter_service_id")["ES1"]["unit_price"] == Decimal("100.00")  # first in file wins
    assert [r["reject_reason"] for r in res.rejected.collect()] == ["DUPLICATE_KEY_CONFLICT"]


def test_lines_for_open_encounter_without_discharge_are_accepted(spark):
    res = _clean_lines(
        spark, [line("ES1", sdate="2026-03-20")], encounters=[("EN0001", "2026-03-01 10:00:00", None)]
    )
    assert res.accepted.count() == 1
