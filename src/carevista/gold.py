"""Task 4 - gold: star schema + KPI tables.

Star schema (no names, emails or phone numbers in gold):
  dim_patient, dim_service, dim_hospital, fct_encounter, fct_billing_line

KPIs are plain SQL files in carevista/sql/, run on Spark SQL (the same files
run unchanged in Databricks SQL). All gold tables are written with overwrite.
"""

from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from .audit import write_audit
from .config import ELIGIBLE_STATUSES, PipelineConfig
from .io import read_delta, write_overwrite
from .rules import cutoff_timestamp

SQL_DIR = Path(__file__).parent / "sql"

KPI_QUERIES = {
    "kpi1_revenue_by_department_month": "kpi1_revenue_by_department_month.sql",
    "kpi2_hospital_encounter_type": "kpi2_hospital_encounter_type.sql",
    "kpi3_top10_patients": "kpi3_top10_patients.sql",
    "kpi4_patient_category_profile": "kpi4_patient_category_profile.sql",
    "kpi5_inpatient_length_of_stay": "kpi5_inpatient_length_of_stay.sql",
    "kpi6_region_service_category_mix": "kpi6_region_service_category_mix.sql",
}

DIMENSIONS_AND_FACTS = ["dim_patient", "dim_service", "dim_hospital", "fct_encounter", "fct_billing_line"]


def build_dim_patient(patients: DataFrame) -> DataFrame:
    # Names, email and phone stay in silver only (privacy).
    return patients.select(
        "patient_id",
        "gender",
        "city",
        "patient_category",
        "date_of_birth",
        "registration_date",
        F.col("last_updated").alias("record_last_updated"),
    )


def build_dim_service(services: DataFrame) -> DataFrame:
    return services.select("service_id", "service_name", "service_category", "department")


def build_dim_hospital(encounters: DataFrame) -> DataFrame:
    """One row per hospital_id, using the attributes on its most recent encounter."""
    w = Window.partitionBy("hospital_id").orderBy(F.col("admit_timestamp").desc(), F.col("encounter_id").asc())
    return (
        encounters.withColumn("_r", F.row_number().over(w))
        .filter("_r = 1")
        .select("hospital_id", "hospital_name", "hospital_city", "hospital_region")
    )


def build_fct_encounter(encounters: DataFrame, cutoff: str) -> DataFrame:
    """Rule E4: an eligible encounter is a valid encounter (passed E1-E3) that is
    Completed or Discharged and was admitted and discharged on or before the cutoff."""
    cutoff_ts = cutoff_timestamp(cutoff)
    eligible = (
        F.col("encounter_status").isin(*ELIGIBLE_STATUSES)
        & (F.col("admit_timestamp") <= cutoff_ts)
        & F.col("discharge_timestamp").isNotNull()
        & (F.col("discharge_timestamp") <= cutoff_ts)
    )
    stay_hours = F.expr("timestampdiff(SECOND, admit_timestamp, discharge_timestamp)") / F.lit(3600)
    return encounters.select(
        "encounter_id",
        "patient_id",
        "hospital_id",
        "encounter_type",
        "encounter_status",
        "admit_timestamp",
        "discharge_timestamp",
        F.to_date("admit_timestamp").alias("admit_date"),
        F.round(stay_hours.cast("decimal(18,4)"), 2).alias("length_of_stay_hours"),
        eligible.alias("is_eligible"),
    )


def build_fct_billing_line(lines: DataFrame) -> DataFrame:
    gross = (F.col("quantity").cast("decimal(10,0)") * F.col("unit_price")).cast("decimal(18,2)")
    return lines.select(
        "encounter_service_id",
        "encounter_id",
        "service_id",
        "service_date",
        F.date_format("service_date", "yyyy-MM").alias("service_month"),
        "quantity",
        "unit_price",
        "discount_pct",
        gross.alias("gross_amount"),
        "line_charge",
    )


def read_sql(file_name: str) -> str:
    return (SQL_DIR / file_name).read_text(encoding="utf-8")


def run_kpis(spark: SparkSession, tables: dict[str, DataFrame]) -> dict[str, DataFrame]:
    for name, df in tables.items():
        df.createOrReplaceTempView(name)
    return {name: spark.sql(read_sql(file_name)) for name, file_name in KPI_QUERIES.items()}


def run(spark: SparkSession, cfg: PipelineConfig) -> list[dict]:
    silver = {e: read_delta(spark, cfg.table("silver", e)) for e in ("patients", "services", "encounters", "encounter_services")}
    built = {
        "dim_patient": build_dim_patient(silver["patients"]),
        "dim_service": build_dim_service(silver["services"]),
        "dim_hospital": build_dim_hospital(silver["encounters"]),
        "fct_encounter": build_fct_encounter(silver["encounters"], cfg.reporting_cutoff),
        "fct_billing_line": build_fct_billing_line(silver["encounter_services"]),
    }
    results = []
    for name, df in built.items():
        write_overwrite(df, cfg.table("gold", name))
    # Re-read from storage so KPIs use exactly what was written.
    stored = {name: read_delta(spark, cfg.table("gold", name)) for name in built}
    for name, df in stored.items():
        n = df.count()
        results.append({"entity": name, "rows_accepted": n, "detail": "gold table"})
        print(f"[gold] {name}: {n} rows")

    for name, df in run_kpis(spark, stored).items():
        write_overwrite(df, cfg.table("gold", name))
        n = read_delta(spark, cfg.table("gold", name)).count()
        results.append({"entity": name, "rows_accepted": n, "detail": "kpi table"})
        print(f"[gold] {name}: {n} rows")

    write_audit(spark, cfg, "gold", results)
    return results
