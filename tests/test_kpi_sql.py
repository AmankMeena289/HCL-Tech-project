"""KPI SQL tested on tiny hand-made star schemas where the answer is known."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from carevista.gold import run_kpis

D = Decimal


def make_tables(spark, patients, encounters, lines, services=None, hospitals=None):
    services = services or [("SV001", "General Consultation", "Consultation", "Consultation"),
                            ("SV005", "Complete Blood Count", "Diagnostic", "Laboratory")]
    hospitals = hospitals or [("H01", "CareVista Delhi Central", "Delhi", "North"),
                              ("H02", "CareVista Chandigarh", "Chandigarh", "North")]
    return {
        "dim_patient": spark.createDataFrame(
            [(p, "Male", "Pune", cat, date(1990, 1, 1), date(2024, 1, 1), datetime(2024, 1, 1)) for p, cat in patients],
            "patient_id string, gender string, city string, patient_category string, date_of_birth date, "
            "registration_date date, record_last_updated timestamp",
        ),
        "dim_service": spark.createDataFrame(
            services, "service_id string, service_name string, service_category string, department string"
        ),
        "dim_hospital": spark.createDataFrame(
            hospitals, "hospital_id string, hospital_name string, hospital_city string, hospital_region string"
        ),
        "fct_encounter": spark.createDataFrame(
            [
                (e, p, h, t, "Completed" if ok else "Cancelled", datetime(2026, 3, 1, 10), datetime(2026, 3, 2, 10),
                 date(2026, 3, 1), D("24.00"), ok)
                for e, p, h, t, ok in encounters
            ],
            "encounter_id string, patient_id string, hospital_id string, encounter_type string, "
            "encounter_status string, admit_timestamp timestamp, discharge_timestamp timestamp, admit_date date, "
            "length_of_stay_hours decimal(18,2), is_eligible boolean",
        ),
        "fct_billing_line": spark.createDataFrame(
            [(l, e, s, sd, sd.strftime("%Y-%m"), 1, D(c), D("0.00"), D(c), D(c)) for l, e, s, sd, c in lines],
            "encounter_service_id string, encounter_id string, service_id string, service_date date, "
            "service_month string, quantity int, unit_price decimal(18,2), discount_pct decimal(5,2), "
            "gross_amount decimal(18,2), line_charge decimal(18,2)",
        ),
    }


def rows(df):
    return [tuple(r) for r in df.collect()]


def test_kpi1_groups_by_month_and_department_and_skips_ineligible(spark):
    t = make_tables(
        spark,
        patients=[("PT1", "Insured")],
        encounters=[("E1", "PT1", "H01", "Outpatient", True), ("E2", "PT1", "H01", "Outpatient", False)],
        lines=[
            ("L1", "E1", "SV001", date(2026, 3, 1), "100.00"),
            ("L2", "E1", "SV001", date(2026, 3, 9), "50.50"),
            ("L3", "E1", "SV005", date(2026, 4, 1), "10.00"),
            ("L4", "E2", "SV001", date(2026, 3, 1), "999.00"),  # cancelled encounter -> excluded
        ],
    )
    assert rows(run_kpis(spark, t)["kpi1_revenue_by_department_month"]) == [
        ("2026-03", "Consultation", D("150.50")),
        ("2026-04", "Laboratory", D("10.00")),
    ]


def test_kpi2_counts_encounters_without_lines_and_rounds_half_up(spark):
    t = make_tables(
        spark,
        patients=[("PT1", "Insured")],
        encounters=[
            ("E1", "PT1", "H01", "Outpatient", True),
            ("E2", "PT1", "H01", "Outpatient", True),
            ("E3", "PT1", "H01", "Outpatient", True),  # no lines -> bill 0, still counted
            ("E4", "PT1", "H02", "Emergency", False),  # not eligible -> no row for H02
        ],
        lines=[("L1", "E1", "SV001", date(2026, 3, 1), "100.00"), ("L2", "E2", "SV001", date(2026, 3, 1), "0.01")],
    )
    # 100.01 / 3 = 33.33666... -> 33.34
    assert rows(run_kpis(spark, t)["kpi2_hospital_encounter_type"]) == [
        ("H01", "Outpatient", 3, D("100.01"), D("33.34"))
    ]


def test_kpi3_ties_broken_by_patient_id_and_only_top_ten(spark):
    patients = [(f"PT{i:02d}", "Insured") for i in range(1, 13)]
    encounters = [(f"E{i:02d}", f"PT{i:02d}", "H01", "Outpatient", True) for i in range(1, 13)]
    # PT03 and PT01 tie on 500; PT01 must rank first.
    amounts = {1: "500.00", 2: "100.00", 3: "500.00"}
    lines = [(f"L{i:02d}", f"E{i:02d}", "SV001", date(2026, 3, 1), amounts.get(i, f"{i}.00")) for i in range(1, 13)]
    out = rows(run_kpis(spark, make_tables(spark, patients, encounters, lines))["kpi3_top10_patients"])
    assert len(out) == 10
    assert out[0] == (1, "PT01", 1, D("500.00"))
    assert out[1] == (2, "PT03", 1, D("500.00"))
    assert [r[1] for r in out] == ["PT01", "PT03", "PT02", "PT12", "PT11", "PT10", "PT09", "PT08", "PT07", "PT06"]
    assert [r[0] for r in out] == list(range(1, 11))


def test_kpi3_output_has_no_personal_columns(spark):
    t = make_tables(spark, [("PT1", "Insured")], [("E1", "PT1", "H01", "Outpatient", True)],
                    [("L1", "E1", "SV001", date(2026, 3, 1), "1.00")])
    assert run_kpis(spark, t)["kpi3_top10_patients"].columns == ["rank", "patient_id", "eligible_encounters", "billed_amount"]


def test_kpi4_category_without_eligible_encounters_has_null_average(spark):
    t = make_tables(
        spark,
        patients=[("PT1", "Insured"), ("PT2", "Insured"), ("PT3", "Corporate")],
        encounters=[
            ("E1", "PT1", "H01", "Outpatient", True),
            ("E2", "PT1", "H01", "Outpatient", True),
            ("E3", "PT3", "H01", "Outpatient", False),  # Corporate has only an ineligible encounter
        ],
        lines=[("L1", "E1", "SV001", date(2026, 3, 1), "100.00"), ("L2", "E2", "SV001", date(2026, 3, 1), "50.00")],
    )
    out = rows(run_kpis(spark, t)["kpi4_patient_category_profile"])
    assert out == [
        ("SelfPay", 0, 0, 0, D("0.00"), None),
        ("Insured", 2, 1, 2, D("150.00"), D("75.00")),
        ("Corporate", 1, 0, 0, D("0.00"), None),
    ]
