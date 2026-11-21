"""Unit tests for the cleansing building blocks in carevista.rules."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from pyspark.sql import functions as F

from carevista import rules as R


def _one_col(spark, values, fn):
    df = spark.createDataFrame([(v,) for v in values], "v string")
    return [r["out"] for r in df.select(fn(F.col("v")).alias("out")).collect()]


def test_clean_text_trims_and_blanks_become_null(spark):
    assert _one_col(spark, ["  Diya", "Kabir ", "   ", "", None], R.clean_text) == ["Diya", "Kabir", None, None, None]


def test_parse_date_accepts_both_formats(spark):
    out = _one_col(spark, ["2026-05-02", "29/03/2026", " 2024-11-11 "], R.parse_date)
    assert out == [date(2026, 5, 2), date(2026, 3, 29), date(2024, 11, 11)]


@pytest.mark.parametrize("bad", ["31/02/2026", "2026/01/01", "03-29-2026", "abc", "", None, "2026-13-01"])
def test_parse_date_rejects_bad_values(spark, bad):
    assert _one_col(spark, [bad], R.parse_date) == [None]


def test_parse_timestamp_accepts_both_formats(spark):
    out = _one_col(
        spark,
        ["2026-01-26 19:39:00", "01/06/2026 11:02", "2026-01-26 19:39", "01/06/2026 11:02:30"],
        R.parse_timestamp,
    )
    assert out == [
        datetime(2026, 1, 26, 19, 39),
        datetime(2026, 6, 1, 11, 2),
        datetime(2026, 1, 26, 19, 39),
        datetime(2026, 6, 1, 11, 2, 30),
    ]


def test_parse_timestamp_dd_mm_is_day_first(spark):
    # 04/01/2026 must be 4 January, not 1 April.
    assert _one_col(spark, ["04/01/2026 20:10"], R.parse_timestamp) == [datetime(2026, 1, 4, 20, 10)]


@pytest.mark.parametrize("bad", ["", None, "yesterday", "2026-01-26T19:39:00", "32/01/2026 10:00"])
def test_parse_timestamp_rejects_bad_values(spark, bad):
    assert _one_col(spark, [bad], R.parse_timestamp) == [None]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1801.00", Decimal("1801.00")),
        ("Rs. 906", Decimal("906.00")),
        ("Rs. 1,234", Decimal("1234.00")),
        ("₹1,234.50", Decimal("1234.50")),
        ("₹999.99", Decimal("999.99")),
        (" 99 ", Decimal("99.00")),
        ("-500.00", Decimal("-500.00")),
        ("Rs. -500", Decimal("-500.00")),
        ("abc", None),
        ("", None),
        (None, None),
        ("12.3.4", None),
    ],
)
def test_parse_amount(spark, raw, expected):
    assert _one_col(spark, [raw], R.parse_amount) == [expected]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("SelfPay", "SelfPay"),
        ("SELF PAY", "SelfPay"),
        ("Self-Pay", "SelfPay"),
        ("selfpay", "SelfPay"),
        ("INSURED", "Insured"),
        ("insured", "Insured"),
        ("corporate", "Corporate"),
        ("CORPORATE", "Corporate"),
        ("Gold", None),
        ("", None),
        (None, None),
    ],
)
def test_standardize_patient_category(spark, raw, expected):
    fn = lambda c: R.standardize_choice(c, ("SelfPay", "Insured", "Corporate"))  # noqa: E731
    assert _one_col(spark, [raw], fn) == [expected]


def test_title_case_department(spark):
    out = _one_col(spark, ["radiology", "PHARMACY", "room & nursing", " consultation "], R.title_case)
    assert out == ["Radiology", "Pharmacy", "Room & Nursing", "Consultation"]


def test_parse_whole_number(spark):
    assert _one_col(spark, ["2", "-1", " 8 ", "1.5", "x", None], R.parse_whole_number) == [2, -1, 8, None, None, None]


def test_parse_discount_blank_means_zero(spark):
    out = _one_col(spark, ["10", "", None, "120", "abc"], R.parse_discount)
    assert out == [Decimal("10.00"), Decimal("0.00"), Decimal("0.00"), Decimal("120.00"), None]


@pytest.mark.parametrize(
    "qty, price, disc, expected",
    [
        (2, "1801.00", "10", Decimal("3241.80")),
        (1, "0.10", "5", Decimal("0.10")),        # 0.095 -> 0.10 (half up, float would give 0.09)
        (1, "1.05", "50", Decimal("0.53")),       # 0.525 -> 0.53
        (3, "333.33", "10", Decimal("899.99")),   # 899.991 -> 899.99
        (1, "100.00", "0", Decimal("100.00")),
        (1, "100.00", "100", Decimal("0.00")),
    ],
)
def test_line_charge_rounds_half_up(spark, qty, price, disc, expected):
    df = spark.createDataFrame([(qty, price, disc)], "q int, p string, d string")
    out = df.select(
        R.line_charge(F.col("q"), F.col("p").cast("decimal(18,2)"), F.col("d").cast("decimal(5,2)")).alias("c")
    ).first()["c"]
    assert out == expected
