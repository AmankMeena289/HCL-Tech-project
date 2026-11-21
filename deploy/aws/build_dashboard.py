"""Build a local dashboard (dashboard/index.html) from the KPI outputs the AWS pipeline wrote.

Inputs:  aws_output/*.csv           (downloaded from s3://<lake>/carevista/reports/)
         aws_output/run.json        (Step Functions + audit facts, written by show_dashboard.sh)
Output:  dashboard/index.html       (self-contained; open via http://localhost:8080)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
src = root / "aws_output"
out = root / "dashboard"
out.mkdir(exist_ok=True)


def rows(name: str) -> list[dict]:
    with open(src / f"{name}.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


data = {
    "kpi1": rows("kpi1_revenue_by_department_month"),
    "kpi2": rows("kpi2_hospital_encounter_type"),
    "kpi3": rows("kpi3_top10_patients"),
    "kpi4": rows("kpi4_patient_category_profile"),
    "kpi5": rows("kpi5_inpatient_length_of_stay"),
    "kpi6": rows("kpi6_region_service_category_mix"),
    "run": json.loads((src / "run.json").read_text(encoding="utf-8")),
}

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CareVista Healthcare Analytics - AWS</title>
<style>
.viz-root{color-scheme:light;--surface-0:#f4f4f2;--surface-1:#fcfcfb;--border:#e4e3df;--grid:#ecebe7;
  --text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#7a7974;--series-1:#2a78d6;--series-1-soft:#d6e6f8;
  --good:#0a7d32;--good-bg:#e5f4ea;--critical:#c4302b;}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-0:#111110;--surface-1:#1a1a19;--border:#2e2d2b;--grid:#262624;
  --text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--series-1:#3987e5;--series-1-soft:#1d3350;
  --good:#3fbf6a;--good-bg:#143321;--critical:#e66767;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--surface-0:#111110;--surface-1:#1a1a19;
  --border:#2e2d2b;--grid:#262624;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--series-1:#3987e5;
  --series-1-soft:#1d3350;--good:#3fbf6a;--good-bg:#143321;--critical:#e66767;}}
*{box-sizing:border-box}
body{margin:0}
.viz-root{background:var(--surface-0);color:var(--text-primary);font:14px/1.45 "Segoe UI",system-ui,-apple-system,Arial,sans-serif;min-height:100vh}
.wrap{max-width:1180px;margin:0 auto;padding:28px 24px 60px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:22px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 2px}
.sub{color:var(--text-secondary);margin:0}
.muted{color:var(--text-muted);font-size:12.5px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:var(--good-bg);color:var(--good);font-weight:600;font-size:13px}
.toolbar{display:flex;gap:8px;align-items:center}
button{font:inherit;font-size:13px;padding:5px 10px;border-radius:6px;border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary);cursor:pointer}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px}
.tile,.card{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:16px}
.tile .label{color:var(--text-secondary);font-size:12.5px}
.tile .value{font-size:26px;font-weight:650;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:16px;margin-bottom:16px}
.card{margin-bottom:16px}.grid2 .card{margin-bottom:0}
.card-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:12px}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid)}
th{color:var(--text-secondary);font-weight:600;font-size:12px}
td.num,th.num{text-align:right}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.step{border:1px solid var(--border);border-radius:8px;padding:10px 12px}
.step .name{font-weight:600}.ok{color:var(--good);font-weight:600}
/* bar charts (HTML) */
.bars{display:flex;flex-direction:column;gap:6px}
.bar-row{display:grid;grid-template-columns:150px 1fr 110px;align-items:center;gap:10px;font-size:13px}
.bar-track{height:18px;position:relative;border-left:1px solid var(--text-muted)}
.bar{height:100%;background:var(--series-1);border-radius:0 4px 4px 0;min-width:2px}
.bar-row:hover .bar,.col:hover .colbar{filter:brightness(1.12)}
.bar-row .v{text-align:right;color:var(--text-secondary)}
.cols{display:flex;align-items:flex-end;gap:2px;height:200px;border-bottom:1px solid var(--text-muted);padding:0 4px;position:relative}
.col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%;padding:0 6px;cursor:default}
.colbar{width:100%;max-width:56px;background:var(--series-1);border-radius:4px 4px 0 0}
.col .top{font-size:12px;color:var(--text-secondary);margin-bottom:4px;white-space:nowrap}
.xlabels{display:flex;gap:2px;padding:4px 4px 0}.xlabels span{flex:1;text-align:center;font-size:12px;color:var(--text-secondary)}
.gridline{position:absolute;left:0;right:0;border-top:1px dashed var(--grid);z-index:0}.col{position:relative;z-index:1}
#tip{position:fixed;pointer-events:none;background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);
  border-radius:6px;padding:6px 9px;font-size:12.5px;box-shadow:0 4px 14px rgba(0,0,0,.14);display:none;z-index:9;max-width:280px}
details summary{cursor:pointer;color:var(--text-secondary);font-size:13px;margin-top:10px}
.check{display:flex;gap:8px;align-items:flex-start;margin:4px 0}
code{font-family:Consolas,monospace;font-size:12.5px}
@media (max-width:700px){.steps{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}.bar-row{grid-template-columns:100px 1fr 90px}}
</style>
</head>
<body>
<div class="viz-root"><div class="wrap">
<header>
  <div>
    <h1>CareVista Healthcare Billing Analytics</h1>
    <p class="sub">Deployed on AWS: S3, Glue (PySpark and Delta Lake), Step Functions, Athena &middot; batch <b id="batch"></b> &middot; cutoff 30 June 2026</p>
  </div>
  <div class="toolbar"><span class="pill" id="status"></span><button id="theme" type="button">Toggle theme</button></div>
</header>

<section class="tiles" id="tiles"></section>

<section class="card">
  <div class="card-head"><div><h2>AWS workflow run</h2><span class="muted" id="runname"></span></div><span class="muted" id="region"></span></div>
  <div class="steps" id="steps"></div>
</section>

<section class="grid2">
  <div class="card">
    <div class="card-head"><h2>Billed revenue by month</h2><span class="muted">INR, all departments (KPI 1)</span></div>
    <div id="chart-month"></div>
    <details><summary>By department (table)</summary><div id="tbl-kpi1"></div></details>
  </div>
  <div class="card">
    <div class="card-head"><h2>Billed amount by hospital</h2><span class="muted">INR, all encounter types (KPI 2)</span></div>
    <div id="chart-hospital"></div>
    <details><summary>By hospital and encounter type (table)</summary><div id="tbl-kpi2"></div></details>
  </div>
</section>

<section class="card">
  <div class="card-head"><h2>Data quality: rows read, accepted and quarantined</h2><span class="muted">silver step, from audit/pipeline_audit</span></div>
  <div id="tbl-audit"></div>
</section>

<section class="grid2">
  <div class="card"><div class="card-head"><h2>Top 10 patients by billed amount</h2><span class="muted">KPI 3 (no PII)</span></div><div id="tbl-kpi3"></div></div>
  <div class="card"><div class="card-head"><h2>Patient category profile</h2><span class="muted">KPI 4</span></div><div id="tbl-kpi4"></div>
    <div class="card-head" style="margin-top:18px"><h2>Inpatient length of stay</h2><span class="muted">KPI 5, days</span></div><div id="tbl-kpi5"></div></div>
</section>

<section class="card"><div class="card-head"><h2>Revenue mix by region and service category</h2><span class="muted">KPI 6</span></div><div id="tbl-kpi6"></div></section>

<section class="grid2">
  <div class="card"><h2>Verification</h2><div id="checks" style="margin-top:8px"></div></div>
  <div class="card"><h2>AWS resources</h2><table id="resources" style="margin-top:8px"></table></div>
</section>
<p class="muted">Generated from the files the AWS pipeline wrote to <code id="src"></code>.</p>
</div></div>
<div id="tip" role="tooltip"></div>

<script>
(() => {
const D = __DATA__;
const $ = id => document.getElementById(id);
const n = v => Number(v);
const inr = v => n(v).toLocaleString("en-IN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const int = v => n(v).toLocaleString("en-IN");
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const short = v => v >= 1e5 ? (v/1e5).toFixed(2) + " L" : v >= 1e3 ? (v/1e3).toFixed(1) + " K" : v.toFixed(0);

// theme toggle (wins over the OS setting both ways)
$("theme").onclick = () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "light" : "dark";
};

// tooltip
const tip = $("tip");
function bindTip(el, html) {
  el.addEventListener("mousemove", e => { tip.innerHTML = html; tip.style.display = "block";
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 290) + "px"; tip.style.top = (e.clientY + 14) + "px"; });
  el.addEventListener("mouseleave", () => tip.style.display = "none");
}

function table(id, rows, cols) {
  const head = cols.map(c => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("");
  const body = rows.map(r => "<tr>" + cols.map(c => {
    const v = c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key]);
    return `<td class="${c.num ? "num" : ""}">${v}</td>`; }).join("") + "</tr>").join("");
  $(id).innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

const R = D.run;
$("batch").textContent = R.batch_id;
$("status").innerHTML = (R.status === "SUCCEEDED" ? "&#10003; Pipeline succeeded" : "Pipeline: " + esc(R.status));
if (R.status !== "SUCCEEDED") { $("status").style.color = "var(--critical)"; }
$("runname").textContent = "Step Functions execution " + R.execution;
$("region").textContent = "Account " + R.account + " · " + R.region;
$("src").textContent = R.reports_uri;

// tiles
const totalRevenue = D.kpi4.reduce((s, r) => s + n(r.billed_amount), 0);
const eligible = D.kpi4.reduce((s, r) => s + n(r.eligible_encounters), 0);
const read = R.audit.reduce((s, r) => s + r.rows_read, 0), acc = R.audit.reduce((s, r) => s + r.rows_accepted, 0);
const tiles = [
  ["Billed revenue (INR)", inr(totalRevenue), "eligible encounters only, excluding tax"],
  ["Eligible encounters", int(eligible), "status Completed or Discharged, before the cutoff"],
  ["Rows accepted", `${int(acc)} / ${int(read)}`, `${int(read - acc)} quarantined with a reason`],
  ["AWS run time", R.total_minutes + " min", "4 Glue tasks run in order, 1 retry each"],
];
$("tiles").innerHTML = tiles.map(t => `<div class="tile"><div class="label">${t[0]}</div><div class="value">${t[1]}</div><div class="muted">${t[2]}</div></div>`).join("");

// workflow steps
$("steps").innerHTML = R.steps.map((s, i) => `<div class="step"><div class="muted">Step ${i + 1}</div>
  <div class="name">${esc(s.name)}</div><div class="ok">&#10003; ${esc(s.status)}</div>
  <div class="muted">${esc(s.duration)} · Glue job ${esc(s.job)}</div></div>`).join("");

// KPI 1 -> monthly totals (column chart)
const byMonth = {};
D.kpi1.forEach(r => byMonth[r.month] = (byMonth[r.month] || 0) + n(r.billed_revenue));
const months = Object.keys(byMonth).sort(), mMax = Math.max(...Object.values(byMonth));
const monthName = m => new Date(m + "-01T00:00:00").toLocaleString("en", {month: "short", year: "numeric"});
const step = Math.pow(10, Math.floor(Math.log10(mMax))), yTop = Math.ceil(mMax / step) * step;
let gl = ""; for (let g = step; g < yTop; g += step) gl += `<div class="gridline" style="bottom:${g / yTop * 100}%"></div>`;
$("chart-month").innerHTML = `<div class="cols">${gl}${months.map(m => `<div class="col" data-m="${m}">
  <div class="top">${short(byMonth[m])}</div><div class="colbar" style="height:${byMonth[m] / yTop * 88}%"></div></div>`).join("")}</div>
  <div class="xlabels">${months.map(m => `<span>${monthName(m)}</span>`).join("")}</div>`;
document.querySelectorAll("#chart-month .col").forEach(el => {
  const m = el.dataset.m;
  const lines = D.kpi1.filter(r => r.month === m).sort((a, b) => n(b.billed_revenue) - n(a.billed_revenue))
    .map(r => `${esc(r.department)}: ${inr(r.billed_revenue)}`).join("<br>");
  bindTip(el, `<b>${monthName(m)}</b> · INR ${inr(byMonth[m])}<br><span style="color:var(--text-secondary)">${lines}</span>`);
});
table("tbl-kpi1", D.kpi1, [{key: "month", label: "Month"}, {key: "department", label: "Department"},
  {key: "billed_revenue", label: "Billed revenue (INR)", num: true, fmt: inr}]);

// KPI 2 -> hospital totals (horizontal bars)
const names = Object.fromEntries(D.kpi5.map(r => [r.hospital_id, r.hospital_name]));
const byHosp = {};
D.kpi2.forEach(r => { const h = byHosp[r.hospital_id] ||= {amt: 0, enc: 0, types: []};
  h.amt += n(r.billed_amount); h.enc += n(r.eligible_encounters); h.types.push(r); });
const hosp = Object.entries(byHosp).sort((a, b) => b[1].amt - a[1].amt), hMax = hosp[0][1].amt;
$("chart-hospital").innerHTML = `<div class="bars">${hosp.map(([id, h]) => `<div class="bar-row" data-h="${id}">
  <span>${esc(names[id] ? names[id].replace("CareVista ", "") : id)} <span class="muted">${id}</span></span>
  <div class="bar-track"><div class="bar" style="width:${h.amt / hMax * 100}%"></div></div>
  <span class="v">${short(h.amt)}</span></div>`).join("")}</div>`;
document.querySelectorAll("#chart-hospital .bar-row").forEach(el => {
  const h = byHosp[el.dataset.h];
  bindTip(el, `<b>${esc(names[el.dataset.h] || el.dataset.h)}</b><br>INR ${inr(h.amt)} · ${h.enc} encounters<br>` +
    h.types.map(t => `<span style="color:var(--text-secondary)">${esc(t.encounter_type)}: ${t.eligible_encounters} enc, avg ${inr(t.average_bill)}</span>`).join("<br>"));
});
table("tbl-kpi2", D.kpi2, [{key: "hospital_id", label: "Hospital"}, {key: "encounter_type", label: "Type"},
  {key: "eligible_encounters", label: "Encounters", num: true}, {key: "billed_amount", label: "Billed (INR)", num: true, fmt: inr},
  {key: "average_bill", label: "Average bill", num: true, fmt: inr}]);

table("tbl-audit", R.audit, [{key: "source_file", label: "Source file"}, {key: "rows_read", label: "Read", num: true},
  {key: "rows_accepted", label: "Accepted", num: true}, {key: "rows_rejected", label: "Quarantined", num: true},
  {key: "detail", label: "Reject reasons", fmt: v => `<span class="muted">${esc(v).replaceAll("; ", "<br>")}</span>`}]);
table("tbl-kpi3", D.kpi3, [{key: "rank", label: "#"}, {key: "patient_id", label: "Patient"},
  {key: "eligible_encounters", label: "Encounters", num: true}, {key: "billed_amount", label: "Billed (INR)", num: true, fmt: inr}]);
table("tbl-kpi4", D.kpi4, [{key: "patient_category", label: "Category"}, {key: "patients", label: "Patients", num: true},
  {key: "eligible_encounters", label: "Encounters", num: true}, {key: "billed_amount", label: "Billed (INR)", num: true, fmt: inr},
  {key: "average_bill", label: "Avg bill", num: true, fmt: inr}]);
table("tbl-kpi5", D.kpi5, [{key: "hospital_name", label: "Hospital"}, {key: "inpatient_encounters", label: "Inpatient", num: true},
  {key: "avg_length_of_stay_days", label: "Avg days", num: true}, {key: "max_length_of_stay_days", label: "Max days", num: true}]);
table("tbl-kpi6", D.kpi6, [{key: "hospital_region", label: "Region"}, {key: "service_category", label: "Service category"},
  {key: "billed_revenue", label: "Billed revenue (INR)", num: true, fmt: inr},
  {key: "share_of_region_pct", label: "Share of region", num: true, fmt: v => n(v).toFixed(2) + "%"}]);

$("checks").innerHTML = R.checks.map(c => `<div class="check"><span class="ok">&#10003;</span><span>${esc(c)}</span></div>`).join("");
$("resources").innerHTML = R.resources.map(r => `<tr><th>${esc(r[0])}</th><td><code>${esc(r[1])}</code></td></tr>`).join("");
})();
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
(out / "index.html").write_text(html, encoding="utf-8")
print(f"dashboard written to {out / 'index.html'}")
