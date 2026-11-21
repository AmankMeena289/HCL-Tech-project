"""Export KPI results and audit counts to CSV, Markdown and a simple HTML page.

This is for easy review on a laptop. In the cloud, the same gold tables are
queried with Databricks SQL (see sql/ and docs/AZURE_DEPLOYMENT.md).
"""

from __future__ import annotations

import csv
import html
from decimal import Decimal
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from .audit import AUDIT_TABLE, RUN_HISTORY_TABLE
from .config import PipelineConfig
from .gold import KPI_QUERIES
from .io import read_delta, table_exists

KPI_TITLES = {
    "kpi1_revenue_by_department_month": "KPI 1 - Billed revenue by department per month (INR)",
    "kpi2_hospital_encounter_type": "KPI 2 - Encounters and average bill by hospital and encounter type (INR)",
    "kpi3_top10_patients": "KPI 3 - Top ten patients by billed amount (INR)",
    "kpi4_patient_category_profile": "KPI 4 - Patient category profile (INR)",
    "kpi5_inpatient_length_of_stay": "Stretch KPI 5 - Average inpatient length of stay by hospital (days)",
    "kpi6_region_service_category_mix": "Stretch KPI 6 - Revenue mix by region and service category (INR)",
}


def _fmt(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, Decimal):
        return f"{value:.2f}" if value.as_tuple().exponent < 0 else str(value)
    return str(value)


def _rows(spark: SparkSession, path: str, order_cols: list[str] | None = None) -> tuple[list[str], list[list[str]]]:
    df = read_delta(spark, path)
    if order_cols:
        df = df.orderBy(*order_cols)
    cols = df.columns
    return cols, [[_fmt(r[c]) for c in cols] for r in df.collect()]


def _md_table(cols: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _html_table(cols: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(v)}</td>" for v in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def write_report(spark: SparkSession, cfg: PipelineConfig, report_dir: str) -> Path:
    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)
    sections: list[tuple[str, list[str], list[list[str]]]] = []

    audit = (
        read_delta(spark, cfg.table("audit", AUDIT_TABLE))
        .filter((F.col("batch_id") == cfg.batch_id) & F.col("step").isin("bronze", "silver"))
        .select("step", "source_file", "rows_read", "rows_accepted", "rows_rejected", "detail")
    )
    a_cols = audit.columns
    a_rows = [[_fmt(r[c]) for c in a_cols] for r in audit.orderBy(F.col("step").desc(), "source_file").collect()]
    sections.append(("Audit - rows read, accepted and rejected per file", a_cols, a_rows))

    for name in KPI_QUERIES:
        cols, rows = _rows(spark, cfg.table("gold", name))
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(cols)
            writer.writerows(rows)
        sections.append((KPI_TITLES[name], cols, rows))

    history_path = cfg.table("audit", RUN_HISTORY_TABLE)
    if table_exists(spark, history_path):
        hist = (
            read_delta(spark, history_path)
            .filter(F.col("batch_id") == cfg.batch_id)
            .orderBy("started_at")
            .select("run_id", "task", "attempt", "status", "started_at", "finished_at", "message")
        )
        h_cols = hist.columns
        sections.append(
            ("Workflow run history (every attempt)", h_cols, [[_fmt(r[c]) for c in h_cols] for r in hist.collect()])
        )

    title = f"CareVista KPI report - batch {cfg.batch_id} (cutoff {cfg.reporting_cutoff})"
    md = [f"# {title}", "", "All amounts are INR, excluding tax. Only eligible encounters (rule E4) are counted.", ""]
    for heading, cols, rows in sections:
        md += [f"## {heading}", "", _md_table(cols, rows), ""]
    (out / "kpi_report.md").write_text("\n".join(md), encoding="utf-8")

    css = (
        "body{font-family:Segoe UI,Arial,sans-serif;margin:2rem;color:#1f2937}"
        "h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:2rem}"
        "table{border-collapse:collapse;font-size:.85rem}"
        "th,td{border:1px solid #d1d5db;padding:4px 8px;text-align:left}"
        "th{background:#f3f4f6}tr:nth-child(even) td{background:#fafafa}"
    )
    body = "".join(f"<h2>{html.escape(h)}</h2>{_html_table(c, r)}" for h, c, r in sections)
    page = (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"<style>{css}</style></head><body><h1>{html.escape(title)}</h1>"
        "<p>All amounts are INR, excluding tax. Only eligible encounters (rule E4) are counted. "
        "No names, emails or phone numbers are shown.</p>"
        f"{body}</body></html>"
    )
    (out / "kpi_report.html").write_text(page, encoding="utf-8")
    print(f"[report] written to {out.resolve()}")
    return out
