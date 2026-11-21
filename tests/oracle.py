"""Independent re-implementation of the cleansing rules and KPIs in plain pandas.

It does NOT import any pipeline code. The end-to-end tests compare the Spark
pipeline's output with the numbers computed here, so a mistake would have to
be made twice, in two different ways, to go unnoticed.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

CUTOFF = datetime(2026, 6, 30, 23, 59, 59)
CENT = Decimal("0.01")


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def _date(v):
    if _blank(v):
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _ts(v):
    if _blank(v):
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _choice(v, allowed):
    key = re.sub(r"[\s\-_]", "", "" if _blank(v) else str(v)).upper()
    return next((a for a in allowed if a.upper() == key), None)


def _amount(v):
    s = re.sub(r"(?i)rs\.?|inr|₹|,|\s", "", "" if _blank(v) else str(v))
    return Decimal(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def _r2(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def load(source_dir: Path) -> dict[str, pd.DataFrame]:
    read = lambda f: pd.read_csv(source_dir / f, dtype=str, keep_default_na=False)  # noqa: E731
    return {
        "patients": read("patients.csv"),
        "services": read("services.csv"),
        "encounters": read("encounters.csv"),
        "encounter_services": read("encounter_services.csv"),
    }


def clean(raw: dict[str, pd.DataFrame]) -> dict:
    # Patients: drop blank id / bad category / bad last_updated, keep latest last_updated.
    pats = {}
    for i, r in raw["patients"].iterrows():
        pid = r.patient_id.strip()
        cat = _choice(r.patient_category, ["SelfPay", "Insured", "Corporate"])
        lu = _ts(r.last_updated)
        if not pid or cat is None or lu is None:
            continue
        if pid not in pats or lu > pats[pid]["last_updated"]:
            pats[pid] = {"patient_id": pid, "patient_category": cat, "last_updated": lu}

    svcs = {}
    for _, r in raw["services"].iterrows():
        sid = r.service_id.strip().upper()
        if sid and sid not in svcs and r.department.strip():
            svcs[sid] = {"service_id": sid, "department": r.department.strip().title(),
                         "service_category": r.service_category.strip().title()}

    encs = {}
    for _, r in raw["encounters"].iterrows():
        eid = r.encounter_id.strip().upper()
        etype = _choice(r.encounter_type, ["Inpatient", "Outpatient", "Emergency"])
        status = _choice(r.encounter_status, ["Completed", "Discharged", "Open", "Cancelled"])
        adm, dis = _ts(r.admit_timestamp), _ts(r.discharge_timestamp)
        if not eid or etype is None or status is None or adm is None:
            continue
        if not _blank(r.discharge_timestamp) and dis is None:
            continue
        if r.patient_id.strip() not in pats or (dis is not None and dis < adm) or adm > CUTOFF:
            continue
        if eid in encs:
            continue
        encs[eid] = {
            "encounter_id": eid, "patient_id": r.patient_id.strip(), "hospital_id": r.hospital_id.strip().upper(),
            "hospital_region": r.hospital_region.strip().title(), "encounter_type": etype,
            "status": status, "admit": adm, "discharge": dis,
            "eligible": status in ("Completed", "Discharged") and adm <= CUTOFF and dis is not None and dis <= CUTOFF,
        }

    lines = {}
    for _, r in raw["encounter_services"].iterrows():
        lid = r.encounter_service_id.strip().upper()
        eid, sid = r.encounter_id.strip().upper(), r.service_id.strip().upper()
        sdate = _date(r.service_date)
        qty = int(r.quantity) if re.fullmatch(r"-?\d+", r.quantity.strip()) else None
        price = _amount(r.unit_price)
        disc = Decimal(0) if _blank(r.discount_pct) else (
            Decimal(r.discount_pct.strip()) if re.fullmatch(r"-?\d+(\.\d+)?", r.discount_pct.strip()) else None)
        if not lid or sdate is None or qty is None or qty <= 0 or price is None or price < 0:
            continue
        if disc is None or disc < 0 or disc > 100 or sdate > CUTOFF.date():
            continue
        if eid not in encs or sid not in svcs:
            continue
        e = encs[eid]
        if sdate < e["admit"].date() or (e["discharge"] is not None and sdate > e["discharge"].date()):
            continue
        if lid in lines:
            continue
        charge = _r2(Decimal(qty) * price * (Decimal(100) - disc) / Decimal(100))
        lines[lid] = {"encounter_service_id": lid, "encounter_id": eid, "service_id": sid,
                      "month": sdate.strftime("%Y-%m"), "line_charge": charge}
    return {"patients": pats, "services": svcs, "encounters": encs, "lines": lines}


def kpis(c: dict) -> dict:
    elig = {k: v for k, v in c["encounters"].items() if v["eligible"]}
    bill = {k: Decimal("0.00") for k in elig}
    for ln in c["lines"].values():
        if ln["encounter_id"] in bill:
            bill[ln["encounter_id"]] += ln["line_charge"]

    k1: dict = {}
    for ln in c["lines"].values():
        if ln["encounter_id"] in elig:
            key = (ln["month"], c["services"][ln["service_id"]]["department"])
            k1[key] = k1.get(key, Decimal("0.00")) + ln["line_charge"]

    k2: dict = {}
    for eid, e in elig.items():
        key = (e["hospital_id"], e["encounter_type"])
        n, total = k2.get(key, (0, Decimal("0.00")))
        k2[key] = (n + 1, total + bill[eid])
    k2 = {k: (n, t, _r2(t / n)) for k, (n, t) in k2.items()}

    per_patient: dict = {}
    for eid, e in elig.items():
        n, t = per_patient.get(e["patient_id"], (0, Decimal("0.00")))
        per_patient[e["patient_id"]] = (n + 1, t + bill[eid])
    ranked = sorted(per_patient.items(), key=lambda kv: (-kv[1][1], kv[0]))[:10]
    k3 = [(i + 1, pid, n, t) for i, (pid, (n, t)) in enumerate(ranked)]

    k4 = {}
    for cat in ("SelfPay", "Insured", "Corporate"):
        pids = {p for p, v in c["patients"].items() if v["patient_category"] == cat}
        es = [eid for eid, e in elig.items() if e["patient_id"] in pids]
        total = sum((bill[e] for e in es), Decimal("0.00"))
        k4[cat] = (len(pids), len(es), total, _r2(total / len(es)) if es else None)

    return {"kpi1": k1, "kpi2": k2, "kpi3": k3, "kpi4": k4}
