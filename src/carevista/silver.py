"""Task 3 - silver: clean, validate, standardise and de-duplicate.

For every source file:
  * good rows  -> silver/<entity>      (typed, trimmed, standardised)
  * bad rows   -> quarantine/<entity>  (original text + reject_reason)
  * counts     -> audit/pipeline_audit (read = accepted + rejected)

Order matters because of references:
  patients -> services -> encounters (need patients) -> encounter_services
  (need encounters and services).

Rule IDs are explained in docs/CLEANSING_RULES.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from . import rules as R
from .audit import write_audit
from .config import (
    ENCOUNTER_STATUSES,
    ENCOUNTER_TYPES,
    PATIENT_CATEGORIES,
    SOURCE_COLUMNS,
    SOURCE_FILES,
    PipelineConfig,
)
from .io import read_delta, write_overwrite

LINEAGE = ["batch_id", "source_file", "source_row_num"]


@dataclass
class SplitResult:
    accepted: DataFrame
    rejected: DataFrame


# ------------------------------------------------------------ generic ----


def _split(df: DataFrame, raw_cols: list[str], clean_cols: list[str]) -> SplitResult:
    """Rows whose _errors array is empty are accepted, the rest rejected."""
    accepted = df.filter(F.size("_errors") == 0).select(*clean_cols, *LINEAGE)
    rejected = df.filter(F.size("_errors") > 0).select(
        *[F.col(f"raw_{c}").alias(c) for c in raw_cols],
        *LINEAGE,
        F.concat_ws("; ", "_errors").alias("reject_reason"),
    )
    return SplitResult(accepted, rejected)


def _dedupe(
    df: DataFrame,
    key: str,
    order_by: list,
    compare_cols: list[str],
    raw_cols: list[str],
    conflict_reason: str = "DUPLICATE_KEY_CONFLICT",
) -> SplitResult:
    """Keep one row per key. The first row by `order_by` wins.

    Dropped rows go to quarantine as EXACT_DUPLICATE (same values as the kept row)
    or `conflict_reason` (same key, different values).
    """
    w = Window.partitionBy(key).orderBy(*order_by)
    ranked = (
        df.withColumn("_fp", R.row_fingerprint(compare_cols))
        .withColumn("_rank", F.row_number().over(w))
        .withColumn("_kept_fp", F.first("_fp").over(w))
    )
    keep = ranked.filter("_rank = 1")
    drop = ranked.filter("_rank > 1").withColumn(
        "_errors",
        F.array(
            F.when(F.col("_fp") == F.col("_kept_fp"), F.lit("EXACT_DUPLICATE")).otherwise(
                F.lit(conflict_reason)
            )
        ),
    )
    clean_cols = [c for c in df.columns if not c.startswith("raw_") and c not in LINEAGE and c != "_errors"]
    accepted = keep.select(*clean_cols, *LINEAGE)
    rejected = drop.select(
        *[F.col(f"raw_{c}").alias(c) for c in raw_cols],
        *LINEAGE,
        F.concat_ws("; ", "_errors").alias("reject_reason"),
    )
    return SplitResult(accepted, rejected)


def _with_raw(df: DataFrame, raw_cols: list[str]) -> DataFrame:
    """Keep an untouched copy of each source column (raw_<name>) for quarantine output."""
    return df.select(*[F.col(c).alias(f"raw_{c}") for c in raw_cols], "_corrupt_record", *LINEAGE)


def _malformed(df: DataFrame) -> list[tuple]:
    return [(F.col("_corrupt_record").isNotNull(), "MALFORMED_ROW")]


# ----------------------------------------------------------- patients ----

PATIENT_COLS = SOURCE_COLUMNS["patients"]


def clean_patients(bronze: DataFrame) -> SplitResult:
    raw = _with_raw(bronze, PATIENT_COLS)
    typed = raw.select(
        "*",
        R.clean_text(F.col("raw_patient_id")).alias("patient_id"),
        R.clean_text(F.col("raw_first_name")).alias("first_name"),
        R.clean_text(F.col("raw_last_name")).alias("last_name"),
        F.lower(R.clean_text(F.col("raw_email"))).alias("email"),
        R.clean_text(F.col("raw_phone")).alias("phone"),
        R.parse_date(F.col("raw_date_of_birth")).alias("date_of_birth"),
        R.title_case(F.col("raw_gender")).alias("gender"),
        R.title_case(F.col("raw_city")).alias("city"),
        R.standardize_choice(F.col("raw_patient_category"), PATIENT_CATEGORIES).alias("patient_category"),
        R.parse_date(F.col("raw_registration_date")).alias("registration_date"),
        R.parse_timestamp(F.col("raw_last_updated")).alias("last_updated"),
    )
    checks = _malformed(typed) + [
        (F.col("patient_id").isNull(), "P1_BLANK_PATIENT_ID"),
        (F.col("patient_category").isNull(), "P2_INVALID_PATIENT_CATEGORY"),
        (F.col("last_updated").isNull(), "P2_INVALID_LAST_UPDATED"),
        (F.col("raw_date_of_birth").isNotNull() & F.col("date_of_birth").isNull(), "P2_INVALID_DATE_OF_BIRTH"),
        (
            F.col("raw_registration_date").isNotNull() & F.col("registration_date").isNull(),
            "P2_INVALID_REGISTRATION_DATE",
        ),
    ]
    validated = typed.withColumn("_errors", R.collect_errors(checks)).drop("_corrupt_record")
    first = _split(validated, PATIENT_COLS, [c for c in PATIENT_COLS])
    # Rule P3: latest last_updated is the current record; file order breaks ties.
    valid = validated.filter(F.size("_errors") == 0).drop("_errors")
    dedup = _dedupe(
        valid,
        key="patient_id",
        order_by=[F.col("last_updated").desc(), F.col("source_row_num").asc()],
        compare_cols=PATIENT_COLS,
        raw_cols=PATIENT_COLS,
        conflict_reason="SUPERSEDED_VERSION",
    )
    return SplitResult(dedup.accepted, first.rejected.unionByName(dedup.rejected))


# ----------------------------------------------------------- services ----

SERVICE_COLS = SOURCE_COLUMNS["services"]


def clean_services(bronze: DataFrame) -> SplitResult:
    raw = _with_raw(bronze, SERVICE_COLS)
    typed = raw.select(
        "*",
        F.upper(R.clean_text(F.col("raw_service_id"))).alias("service_id"),
        R.clean_text(F.col("raw_service_name")).alias("service_name"),
        R.title_case(F.col("raw_service_category")).alias("service_category"),
        R.title_case(F.col("raw_department")).alias("department"),
    )
    checks = _malformed(typed) + [
        (F.col("service_id").isNull(), "S1_BLANK_SERVICE_ID"),
        (F.col("department").isNull(), "S1_BLANK_DEPARTMENT"),
    ]
    validated = typed.withColumn("_errors", R.collect_errors(checks)).drop("_corrupt_record")
    first = _split(validated, SERVICE_COLS, SERVICE_COLS)
    valid = validated.filter(F.size("_errors") == 0).drop("_errors")
    dedup = _dedupe(
        valid,
        key="service_id",
        order_by=[F.col("source_row_num").asc()],
        compare_cols=SERVICE_COLS,
        raw_cols=SERVICE_COLS,
    )
    return SplitResult(dedup.accepted, first.rejected.unionByName(dedup.rejected))


# --------------------------------------------------------- encounters ----

ENCOUNTER_COLS = SOURCE_COLUMNS["encounters"]


def clean_encounters(bronze: DataFrame, patients: DataFrame, cutoff: str) -> SplitResult:
    raw = _with_raw(bronze, ENCOUNTER_COLS)
    known_patients = patients.select(F.col("patient_id").alias("_known_patient")).distinct()
    typed = raw.select(
        "*",
        F.upper(R.clean_text(F.col("raw_encounter_id"))).alias("encounter_id"),
        R.clean_text(F.col("raw_patient_id")).alias("patient_id"),
        F.upper(R.clean_text(F.col("raw_hospital_id"))).alias("hospital_id"),
        R.clean_text(F.col("raw_hospital_name")).alias("hospital_name"),
        R.title_case(F.col("raw_hospital_city")).alias("hospital_city"),
        R.title_case(F.col("raw_hospital_region")).alias("hospital_region"),
        R.standardize_choice(F.col("raw_encounter_type"), ENCOUNTER_TYPES).alias("encounter_type"),
        R.parse_timestamp(F.col("raw_admit_timestamp")).alias("admit_timestamp"),
        R.parse_timestamp(F.col("raw_discharge_timestamp")).alias("discharge_timestamp"),
        R.standardize_choice(F.col("raw_encounter_status"), ENCOUNTER_STATUSES).alias("encounter_status"),
    ).join(known_patients, F.col("patient_id") == F.col("_known_patient"), "left")

    cutoff_ts = R.cutoff_timestamp(cutoff)
    raw_discharge_given = R.clean_text(F.col("raw_discharge_timestamp")).isNotNull()
    checks = _malformed(typed) + [
        (F.col("encounter_id").isNull(), "E1_BLANK_ENCOUNTER_ID"),
        (F.col("hospital_id").isNull(), "E1_BLANK_HOSPITAL_ID"),
        (F.col("encounter_type").isNull(), "E2_INVALID_ENCOUNTER_TYPE"),
        (F.col("encounter_status").isNull(), "E2_INVALID_ENCOUNTER_STATUS"),
        (F.col("admit_timestamp").isNull(), "E2_INVALID_ADMIT_TIMESTAMP"),
        (raw_discharge_given & F.col("discharge_timestamp").isNull(), "E2_INVALID_DISCHARGE_TIMESTAMP"),
        (F.col("patient_id").isNull() | F.col("_known_patient").isNull(), "E3_UNKNOWN_PATIENT"),
        (F.col("discharge_timestamp") < F.col("admit_timestamp"), "E3_DISCHARGE_BEFORE_ADMIT"),
        (F.col("admit_timestamp") > cutoff_ts, "E3_ADMIT_AFTER_CUTOFF"),
    ]
    validated = (
        typed.withColumn("_errors", R.collect_errors(checks)).drop("_corrupt_record", "_known_patient")
    )
    first = _split(validated, ENCOUNTER_COLS, ENCOUNTER_COLS)
    valid = validated.filter(F.size("_errors") == 0).drop("_errors")
    dedup = _dedupe(
        valid,
        key="encounter_id",
        order_by=[F.col("source_row_num").asc()],
        compare_cols=ENCOUNTER_COLS,
        raw_cols=ENCOUNTER_COLS,
    )
    return SplitResult(dedup.accepted, first.rejected.unionByName(dedup.rejected))


# ------------------------------------------------- encounter services ----

LINE_COLS = SOURCE_COLUMNS["encounter_services"]


def clean_encounter_services(
    bronze: DataFrame,
    encounters: DataFrame,
    bronze_encounter_ids: DataFrame,
    services: DataFrame,
    cutoff: str,
) -> SplitResult:
    raw = _with_raw(bronze, LINE_COLS)
    enc = encounters.select(
        F.col("encounter_id").alias("_enc_id"),
        F.to_date("admit_timestamp").alias("_admit_date"),
        F.to_date("discharge_timestamp").alias("_discharge_date"),
    )
    seen_enc = bronze_encounter_ids.select(F.col("encounter_id").alias("_seen_enc_id")).distinct()
    svc = services.select(F.col("service_id").alias("_svc_id"))

    typed = (
        raw.select(
            "*",
            F.upper(R.clean_text(F.col("raw_encounter_service_id"))).alias("encounter_service_id"),
            F.upper(R.clean_text(F.col("raw_encounter_id"))).alias("encounter_id"),
            F.upper(R.clean_text(F.col("raw_service_id"))).alias("service_id"),
            R.parse_date(F.col("raw_service_date")).alias("service_date"),
            R.parse_whole_number(F.col("raw_quantity")).alias("quantity"),
            R.parse_amount(F.col("raw_unit_price")).alias("unit_price"),
            R.parse_discount(F.col("raw_discount_pct")).alias("discount_pct"),
        )
        .join(enc, F.col("encounter_id") == F.col("_enc_id"), "left")
        .join(seen_enc, F.col("encounter_id") == F.col("_seen_enc_id"), "left")
        .join(svc, F.col("service_id") == F.col("_svc_id"), "left")
    )
    cutoff_date = F.to_date(F.lit(cutoff[:10]), "yyyy-MM-dd")
    encounter_missing = F.col("_enc_id").isNull()
    checks = _malformed(typed) + [
        (F.col("encounter_service_id").isNull(), "L1_BLANK_LINE_ID"),
        (F.col("service_date").isNull(), "L2_INVALID_SERVICE_DATE"),
        (F.col("quantity").isNull(), "L2_INVALID_QUANTITY"),
        (F.col("quantity") <= 0, "L2_NON_POSITIVE_QUANTITY"),
        (F.col("unit_price").isNull(), "L2_INVALID_UNIT_PRICE"),
        (F.col("unit_price") < 0, "L2_NEGATIVE_UNIT_PRICE"),
        (F.col("discount_pct").isNull(), "L2_INVALID_DISCOUNT"),
        ((F.col("discount_pct") < 0) | (F.col("discount_pct") > 100), "L2_DISCOUNT_OUT_OF_RANGE"),
        (F.col("service_date") > cutoff_date, "L2_SERVICE_AFTER_CUTOFF"),
        (encounter_missing & F.col("_seen_enc_id").isNull(), "L4_UNKNOWN_ENCOUNTER"),
        (encounter_missing & F.col("_seen_enc_id").isNotNull(), "L4_ENCOUNTER_REJECTED"),
        (F.col("_svc_id").isNull(), "L4_UNKNOWN_SERVICE"),
        (~encounter_missing & (F.col("service_date") < F.col("_admit_date")), "L4_SERVICE_BEFORE_ADMIT"),
        (
            ~encounter_missing
            & F.col("_discharge_date").isNotNull()
            & (F.col("service_date") > F.col("_discharge_date")),
            "L4_SERVICE_AFTER_DISCHARGE",
        ),
    ]
    validated = (
        typed.withColumn("_errors", R.collect_errors(checks))
        .withColumn("line_charge", R.line_charge(F.col("quantity"), F.col("unit_price"), F.col("discount_pct")))
        .drop("_corrupt_record", "_enc_id", "_seen_enc_id", "_svc_id", "_admit_date", "_discharge_date")
    )
    clean_cols = LINE_COLS + ["line_charge"]
    first = _split(validated, LINE_COLS, clean_cols)
    valid = validated.filter(F.size("_errors") == 0).drop("_errors")
    dedup = _dedupe(
        valid,
        key="encounter_service_id",
        order_by=[F.col("source_row_num").asc()],
        compare_cols=LINE_COLS,
        raw_cols=LINE_COLS,
    )
    return SplitResult(dedup.accepted, first.rejected.unionByName(dedup.rejected))


# ---------------------------------------------------------------- job ----


def _persist(spark: SparkSession, cfg: PipelineConfig, entity: str, result: SplitResult, bronze: DataFrame) -> dict:
    write_overwrite(result.accepted, cfg.table("silver", entity))
    write_overwrite(result.rejected, cfg.table("quarantine", entity))
    accepted = read_delta(spark, cfg.table("silver", entity))
    rejected = read_delta(spark, cfg.table("quarantine", entity))
    n_read, n_ok, n_bad = bronze.count(), accepted.count(), rejected.count()
    if n_read != n_ok + n_bad:
        raise RuntimeError(f"{entity}: rows read ({n_read}) != accepted ({n_ok}) + rejected ({n_bad})")
    reasons = (
        rejected.groupBy("reject_reason").count().orderBy(F.col("count").desc(), "reject_reason").collect()
    )
    detail = "; ".join(f"{r['reject_reason']}={r['count']}" for r in reasons) or "no rejects"
    print(f"[silver] {SOURCE_FILES[entity]}: read={n_read} accepted={n_ok} rejected={n_bad} ({detail})")
    return {
        "entity": entity,
        "source_file": SOURCE_FILES[entity],
        "rows_read": n_read,
        "rows_accepted": n_ok,
        "rows_rejected": n_bad,
        "detail": detail,
    }


def run(spark: SparkSession, cfg: PipelineConfig) -> list[dict]:
    def bronze(entity: str) -> DataFrame:
        return read_delta(spark, cfg.table("bronze", entity)).filter(F.col("batch_id") == cfg.batch_id)

    results = []

    b_pat = bronze("patients")
    results.append(_persist(spark, cfg, "patients", clean_patients(b_pat), b_pat))
    patients = read_delta(spark, cfg.table("silver", "patients"))

    b_svc = bronze("services")
    results.append(_persist(spark, cfg, "services", clean_services(b_svc), b_svc))
    services = read_delta(spark, cfg.table("silver", "services"))

    b_enc = bronze("encounters")
    results.append(
        _persist(spark, cfg, "encounters", clean_encounters(b_enc, patients, cfg.reporting_cutoff), b_enc)
    )
    encounters = read_delta(spark, cfg.table("silver", "encounters"))

    b_lines = bronze("encounter_services")
    bronze_enc_ids = b_enc.select(F.upper(R.clean_text(F.col("encounter_id"))).alias("encounter_id"))
    lines = clean_encounter_services(b_lines, encounters, bronze_enc_ids, services, cfg.reporting_cutoff)
    results.append(_persist(spark, cfg, "encounter_services", lines, b_lines))

    write_audit(spark, cfg, "silver", results)
    return results
