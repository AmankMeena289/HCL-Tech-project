"""Reusable cleansing building blocks (PySpark Column expressions).

Each function takes a raw string column and returns a cleaned/typed column.
A value that cannot be cleaned becomes NULL; the silver job then turns that
NULL into a named reject reason, so nothing fails silently.

Rule IDs (P1, S1, E1, L1, ...) are documented in docs/CLEANSING_RULES.md.
"""

from __future__ import annotations

from typing import Iterable

from pyspark.sql import Column
from pyspark.sql import functions as F

# ---------------------------------------------------------------- text ----


def clean_text(col: Column) -> Column:
    """Trim spaces; an empty string becomes NULL."""
    trimmed = F.trim(col)
    return F.when(trimmed == "", F.lit(None)).otherwise(trimmed)


def is_blank(col: Column) -> Column:
    return col.isNull() | (F.trim(col) == "")


def standardize_choice(col: Column, allowed: Iterable[str]) -> Column:
    """Match a value to an allowed list ignoring case, spaces, '-' and '_'.

    'SELF PAY', 'Self-Pay' and 'selfpay' all become 'SelfPay'.
    Anything not in the list becomes NULL.
    """
    key = F.upper(F.regexp_replace(F.coalesce(col, F.lit("")), r"[\s\-_]", ""))
    result = F.lit(None).cast("string")
    for value in allowed:
        result = F.when(key == value.upper(), F.lit(value)).otherwise(result)
    return result


def title_case(col: Column) -> Column:
    """'radiology' -> 'Radiology', 'room & nursing' -> 'Room & Nursing'."""
    return F.initcap(F.lower(clean_text(col)))


# --------------------------------------------------------------- dates ----

_DATE_ISO = r"^\d{4}-\d{2}-\d{2}$"
_DATE_DMY = r"^\d{2}/\d{2}/\d{4}$"
_TS_ISO_SEC = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
_TS_ISO_MIN = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"
_TS_DMY_SEC = r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$"
_TS_DMY_MIN = r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$"


def parse_date(col: Column) -> Column:
    """Accept YYYY-MM-DD or DD/MM/YYYY. Impossible dates (31/02/2026) -> NULL."""
    c = F.trim(col)
    return (
        F.when(c.rlike(_DATE_ISO), F.to_date(c, "yyyy-MM-dd"))
        .when(c.rlike(_DATE_DMY), F.to_date(c, "dd/MM/yyyy"))
        .otherwise(F.lit(None).cast("date"))
    )


TIMESTAMP_TYPE = "timestamp_ntz"


def _ntz(c: Column, fmt: str) -> Column:
    return F.to_timestamp_ntz(c, F.lit(fmt))


def parse_timestamp(col: Column) -> Column:
    """Accept 'YYYY-MM-DD HH:mm[:ss]' or 'DD/MM/YYYY HH:mm[:ss]'. Else NULL.

    Result is TIMESTAMP_NTZ (no time zone): the source is already Asia/Kolkata
    local time, so the wall-clock value is stored exactly as written and is
    never shifted by a server or session time zone.
    """
    c = F.trim(col)
    return (
        F.when(c.rlike(_TS_ISO_SEC), _ntz(c, "yyyy-MM-dd HH:mm:ss"))
        .when(c.rlike(_TS_ISO_MIN), _ntz(c, "yyyy-MM-dd HH:mm"))
        .when(c.rlike(_TS_DMY_SEC), _ntz(c, "dd/MM/yyyy HH:mm:ss"))
        .when(c.rlike(_TS_DMY_MIN), _ntz(c, "dd/MM/yyyy HH:mm"))
        .otherwise(F.lit(None).cast(TIMESTAMP_TYPE))
    )


def cutoff_timestamp(cutoff: str) -> Column:
    """The reporting cutoff as a TIMESTAMP_NTZ literal."""
    return _ntz(F.lit(cutoff), "yyyy-MM-dd HH:mm:ss")


# ------------------------------------------------------------- numbers ----

AMOUNT_TYPE = "decimal(18,2)"
PERCENT_TYPE = "decimal(5,2)"


def parse_amount(col: Column) -> Column:
    """'Rs. 1,234', '₹1,234.50', '1234.00' -> 1234.00 (decimal). Bad text -> NULL.

    Negative values are kept here so the silver job can reject them with a clear reason.
    """
    stripped = F.regexp_replace(F.coalesce(col, F.lit("")), r"(?i)rs\.?|inr|₹|,|\s", "")
    return F.when(stripped.rlike(r"^-?\d+(\.\d+)?$"), stripped.cast(AMOUNT_TYPE)).otherwise(
        F.lit(None).cast(AMOUNT_TYPE)
    )


def parse_whole_number(col: Column) -> Column:
    """'2' -> 2, '-1' -> -1, '1.5' or 'abc' -> NULL."""
    c = F.trim(col)
    return F.when(c.rlike(r"^-?\d+$"), c.cast("int")).otherwise(F.lit(None).cast("int"))


def parse_discount(col: Column) -> Column:
    """Blank discount means no discount (0). Bad text -> NULL."""
    c = F.trim(col)
    return (
        F.when(c.isNull() | (c == ""), F.lit(0).cast(PERCENT_TYPE))
        .when(c.rlike(r"^-?\d+(\.\d+)?$"), c.cast(PERCENT_TYPE))
        .otherwise(F.lit(None).cast(PERCENT_TYPE))
    )


def line_charge(quantity: Column, unit_price: Column, discount_pct: Column) -> Column:
    """Rule L3: quantity x unit_price x (1 - discount_pct/100), rounded to 2 decimals half up.

    Decimal arithmetic is used throughout so there is no floating point drift.
    Spark's round() on decimals rounds HALF_UP.
    """
    gross = quantity.cast("decimal(10,0)") * unit_price.cast(AMOUNT_TYPE)
    net = gross * (F.lit(100).cast("decimal(5,2)") - discount_pct.cast(PERCENT_TYPE)) / F.lit(100).cast(
        "decimal(5,0)"
    )
    return F.round(net, 2).cast(AMOUNT_TYPE)


# ------------------------------------------------------- reject helpers ----


def collect_errors(checks: list[tuple[Column, str]]) -> Column:
    """Turn (condition, reason) pairs into an array of reasons that apply."""
    reasons = F.array(*[F.when(cond, F.lit(reason)) for cond, reason in checks])
    return F.filter(reasons, lambda x: x.isNotNull())


def row_fingerprint(cols: list[str]) -> Column:
    """Hash of the business columns, used to tell exact duplicates from conflicting ones."""
    return F.sha2(F.concat_ws("\u0001", *[F.coalesce(F.col(c).cast("string"), F.lit("\u0000")) for c in cols]), 256)
