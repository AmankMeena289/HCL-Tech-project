/* CareVista Billing KPIs - local dashboard.
   Reads data/results.json, written by deploy/aws/export_results.py from the latest AWS run. */
(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const SVGNS = 'http://www.w3.org/2000/svg';
  const num = (v) => (v === null || v === undefined || v === '' ? NaN : Number(v));
  const inr = (v) => num(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const int = (v) => num(v).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  const lakh = (v) => '₹' + (v / 100000).toLocaleString('en-IN', { maximumFractionDigits: 2 }) + ' L';
  const series = (i) => `var(--s${(i % 6) + 1})`;
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthLabel = (ym, short) => { const [y, m] = ym.split('-'); return MONTHS[+m - 1] + (short ? '' : ' ' + y); };
  const fmtTime = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
  };

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v);
    }
    (children || []).forEach((c) => n.append(c));
    return n;
  }
  function svg(tag, attrs, text) {
    const n = document.createElementNS(SVGNS, tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (k === 'style') n.style.cssText = v; else n.setAttribute(k, v);
    }
    if (text !== undefined) n.textContent = text;
    return n;
  }

  // ---- tooltip ----
  const tipEl = $('#tip');
  function bindTip(node, lines) {
    node.addEventListener('pointermove', (ev) => {
      tipEl.textContent = lines.join('\n');
      tipEl.hidden = false;
      const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
      let x = ev.clientX + 14, y = ev.clientY + 14;
      if (x + w > window.innerWidth - 8) x = ev.clientX - w - 14;
      if (y + h > window.innerHeight - 8) y = ev.clientY - h - 14;
      tipEl.style.left = Math.max(8, x) + 'px';
      tipEl.style.top = Math.max(8, y) + 'px';
    });
    node.addEventListener('pointerleave', () => { tipEl.hidden = true; });
  }

  // ---- text measuring for chart margins ----
  function textWidth(root, labels, cls) {
    const t = svg('text', { class: cls || '' });
    root.appendChild(t);
    let w = 0;
    labels.forEach((l) => { t.textContent = l; w = Math.max(w, t.getComputedTextLength()); });
    root.removeChild(t);
    return Math.ceil(w);
  }
  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  }
  function ticks(max, n) {
    const step = niceMax(max / n);
    const out = [];
    for (let v = 0; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  }
  function legend(box, keys) {
    box.append(el('div', { class: 'legend' }, keys.map((k, i) => {
      const sw = el('i'); sw.style.background = series(i);
      return el('span', null, [sw, k]);
    })));
  }
  function emptyNote(box, text) { box.replaceChildren(el('p', { class: 'empty', text })); }

  // ---- charts ----
  function stackedMonthly(box, rows) {
    box.replaceChildren();
    if (!rows.length) return emptyNote(box, 'No rows in KPI 1.');
    const months = [...new Set(rows.map((r) => r.month))].sort();
    const depts = [...new Set(rows.map((r) => r.department))];
    const val = (m, d) => rows.filter((r) => r.month === m && r.department === d).reduce((a, r) => a + num(r.billed_revenue), 0);
    const totals = months.map((m) => depts.reduce((a, d) => a + val(m, d), 0));
    legend(box, depts);
    const W = Math.max(300, box.clientWidth), H = 280, top = 22, bottom = 26;
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Stacked bars of billed revenue per month by department' });
    box.append(root);
    const max = niceMax(Math.max(...totals) * 1.05);
    const tv = ticks(max, 5);
    const left = textWidth(root, tv.map(lakh)) + 12;
    const y = (v) => H - bottom - (v / max) * (H - top - bottom);
    tv.forEach((v) => {
      root.append(svg('line', { class: 'grid', x1: left, x2: W, y1: y(v), y2: y(v) }));
      root.append(svg('text', { x: left - 8, y: y(v), 'text-anchor': 'end', 'dominant-baseline': 'middle' }, v === 0 ? '0' : lakh(v)));
    });
    const band = (W - left) / months.length, bw = Math.min(64, band * 0.62);
    const short = band < 70;
    months.forEach((m, i) => {
      const cx = left + band * i + band / 2;
      let acc = 0;
      depts.forEach((d, j) => {
        const v = val(m, d);
        if (!v) return;
        const r = svg('rect', { x: cx - bw / 2, width: bw, y: y(acc + v), height: Math.max(0, y(acc) - y(acc + v)), style: `fill:${series(j)}` });
        bindTip(r, [monthLabel(m), d + ': ₹' + inr(v), 'Month total: ₹' + inr(totals[i])]);
        root.append(r);
        acc += v;
      });
      root.append(svg('text', { class: 'val', x: cx, y: y(totals[i]) - 6, 'text-anchor': 'middle' }, short ? (totals[i] / 100000).toFixed(1) : lakh(totals[i])));
      root.append(svg('text', { x: cx, y: H - 8, 'text-anchor': 'middle' }, monthLabel(m, short)));
    });
    root.append(svg('line', { class: 'axis', x1: left, x2: W, y1: y(0), y2: y(0) }));
  }

  function hbars(box, items, o) {
    box.replaceChildren();
    if (!items.length) return emptyNote(box, 'No rows.');
    const row = 30, top = 4, H = top + items.length * row + 24;
    const W = Math.max(280, box.clientWidth);
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.label });
    box.append(root);
    const left = textWidth(root, items.map((d) => d.name)) + 12;
    const right = textWidth(root, items.map((d) => o.fmt(d.v)), 'val') + 12;
    const max = niceMax(Math.max(...items.map((d) => Math.max(d.v, d.max || 0))));
    const x = (v) => left + (v / max) * (W - left - right);
    const base = top + items.length * row;
    const tv = ticks(max, Math.max(2, Math.floor((W - left - right) / 90)));
    tv.forEach((v) => {
      root.append(svg('line', { class: 'grid', x1: x(v), x2: x(v), y1: top, y2: base }));
      root.append(svg('text', { x: x(v), y: base + 16, 'text-anchor': 'middle' }, o.tick(v)));
    });
    items.forEach((d, i) => {
      const yb = top + i * row + 5, bh = row - 10;
      root.append(svg('text', { x: left - 8, y: yb + bh / 2, 'text-anchor': 'end', 'dominant-baseline': 'middle' }, d.name));
      const r = svg('rect', { x: left, y: yb, width: Math.max(0, x(d.v) - left), height: bh, rx: 2, style: `fill:${series(0)}` });
      bindTip(r, o.tip(d));
      root.append(r);
      let end = x(d.v);
      if (d.max) {
        root.append(svg('line', { x1: x(d.max), x2: x(d.max), y1: yb - 3, y2: yb + bh + 3, style: 'stroke:var(--ink);stroke-width:2' }));
        end = Math.max(end, x(d.max));
      }
      root.append(svg('text', { class: 'val', x: end + 6, y: yb + bh / 2, 'dominant-baseline': 'middle' }, o.fmt(d.v)));
    });
  }

  // grouped vertical bars: one group per hospital, one bar per encounter type
  function groupedBars(box, rows, names) {
    box.replaceChildren();
    if (!rows.length) return emptyNote(box, 'No rows in KPI 2.');
    const groups = [...new Set(rows.map((r) => r.hospital_id))].sort();
    const types = [...new Set(rows.map((r) => r.encounter_type))].sort();
    legend(box, types);
    const W = Math.max(300, box.clientWidth), H = 290, top = 10, bottom = 44;
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Average bill per encounter type for each hospital' });
    box.append(root);
    const max = niceMax(Math.max(...rows.map((r) => num(r.average_bill))) * 1.05);
    const tv = ticks(max, 5);
    const tfmt = (v) => (v === 0 ? '0' : '₹' + (v >= 1000 ? (v / 1000) + 'k' : v));
    const left = textWidth(root, tv.map(tfmt)) + 12;
    const y = (v) => H - bottom - (v / max) * (H - top - bottom);
    tv.forEach((v) => {
      root.append(svg('line', { class: 'grid', x1: left, x2: W, y1: y(v), y2: y(v) }));
      root.append(svg('text', { x: left - 8, y: y(v), 'text-anchor': 'end', 'dominant-baseline': 'middle' }, tfmt(v)));
    });
    const band = (W - left) / groups.length;
    const inner = band * 0.8, bw = inner / types.length;
    groups.forEach((g, i) => {
      const x0 = left + band * i + (band - inner) / 2;
      types.forEach((t, j) => {
        const r = rows.find((d) => d.hospital_id === g && d.encounter_type === t);
        if (!r) return;
        const v = num(r.average_bill);
        const rect = svg('rect', { x: x0 + j * bw + 1, width: Math.max(1, bw - 2), y: y(v), height: Math.max(0, y(0) - y(v)), rx: 1, style: `fill:${series(j)}` });
        bindTip(rect, [(names[g] || g) + ' · ' + t, 'Average bill ₹' + inr(v), int(r.eligible_encounters) + ' eligible encounters', 'Billed ₹' + inr(r.billed_amount)]);
        root.append(rect);
        if (bw >= 16) root.append(svg('text', { x: x0 + j * bw + bw / 2, y: H - bottom + 14, 'text-anchor': 'middle' }, int(r.eligible_encounters)));
      });
      root.append(svg('text', { class: 'val', x: left + band * i + band / 2, y: H - 8, 'text-anchor': 'middle' }, g));
    });
    root.append(svg('line', { class: 'axis', x1: left, x2: W, y1: y(0), y2: y(0) }));
  }

  function regionMix(box, rows) {
    box.replaceChildren();
    if (!rows.length) return emptyNote(box, 'No rows in KPI 6.');
    const regions = [...new Set(rows.map((r) => r.hospital_region))];
    const cats = [...new Set(rows.map((r) => r.service_category))];
    legend(box, cats);
    const row = 44, H = regions.length * row + 26, W = Math.max(280, box.clientWidth);
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Each region\'s revenue split by service category, in percent' });
    box.append(root);
    const left = textWidth(root, regions) + 12;
    const x = (p) => left + (p / 100) * (W - left - 4);
    [0, 25, 50, 75, 100].forEach((p) => root.append(svg('text', { x: x(p), y: H - 6, 'text-anchor': p === 0 ? 'start' : p === 100 ? 'end' : 'middle' }, p + '%')));
    regions.forEach((g, i) => {
      const yb = i * row + 8, bh = row - 16;
      root.append(svg('text', { x: left - 8, y: yb + bh / 2, 'text-anchor': 'end', 'dominant-baseline': 'middle' }, g));
      let acc = 0;
      cats.forEach((c, j) => {
        const d = rows.find((r) => r.hospital_region === g && r.service_category === c);
        if (!d) return;
        const p = num(d.share_of_region_pct);
        const r = svg('rect', { x: x(acc), y: yb, width: Math.max(0, x(acc + p) - x(acc)), height: bh, style: `fill:${series(j)}` });
        bindTip(r, [g + ' · ' + c, p.toFixed(2) + '% of region revenue', '₹' + inr(d.billed_revenue)]);
        root.append(r);
        if (x(acc + p) - x(acc) > 38) root.append(svg('text', { class: 'inbar', x: x(acc) + 6, y: yb + bh / 2, 'dominant-baseline': 'middle' }, Math.round(p) + '%'));
        acc += p;
      });
    });
  }

  // ---- sections ----
  function renderPipeline(p) {
    const steps = p.steps || [];
    const done = steps.filter((s) => s.status === 'SUCCEEDED').length;
    const pct = steps.length ? Math.round((done / steps.length) * 100) : 0;
    $('#pct').textContent = pct;
    const bar = $('#pct-bar');
    bar.setAttribute('aria-valuenow', pct);
    requestAnimationFrame(() => { bar.querySelector('i').style.width = pct + '%'; });
    const ex = p.execution;
    const meta = $('#run-meta');
    meta.replaceChildren();
    if (ex) {
      const glueSecs = steps.reduce((a, s) => a + (num(s.glue_seconds) || 0), 0);
      meta.append(
        el('span', { text: `${done} of ${steps.length} steps succeeded` }),
        el('span', { text: 'Run ' + ex.name }),
        el('span', { text: 'Started ' + fmtTime(ex.started_at) }),
        el('span', { text: ex.finished_at ? 'Finished ' + fmtTime(ex.finished_at) : 'Still running' }),
        el('span', { text: 'Glue compute ' + (glueSecs / 60).toFixed(1) + ' min' }),
      );
      const a = el('a', { href: ex.console_url, target: '_blank', rel: 'noopener', text: 'Open in AWS console' });
      meta.append(a);
    } else {
      meta.append(el('span', { text: 'No pipeline run found yet.' }));
    }
    const desc = {
      landing: 'Copies the four CSVs unchanged and checks SHA-256',
      bronze: 'Loads raw text with batch_id, source_file and row number',
      silver: 'Cleans and validates; bad rows go to quarantine',
      gold: 'Builds the star schema and the six KPI tables',
    };
    $('#steps').replaceChildren(...steps.map((s, i) => {
      const cls = s.status === 'SUCCEEDED' ? 'ok' : s.status === 'FAILED' ? 'bad' : s.status === 'RUNNING' ? 'run' : '';
      const li = el('li', { class: 'step' + (cls ? ' is-' + cls : '') }, [
        el('span', { class: 'step-n', text: 'Step ' + (i + 1) }),
        el('span', { class: 'step-name', text: s.task.charAt(0).toUpperCase() + s.task.slice(1) }),
        el('p', { class: 'step-desc', text: desc[s.task] || '' }),
        el('span', { class: 'pill ' + cls, text: s.status.charAt(0) + s.status.slice(1).toLowerCase() }),
        el('div', { class: 'step-meta' }, [
          el('div', null, [el('span', { text: 'Glue run time ' }), s.glue_seconds != null ? s.glue_seconds + ' s' : '—']),
          el('div', null, [el('span', { text: 'Step time incl. start-up ' }), s.duration_s != null ? s.duration_s + ' s' : '—']),
          el('div', null, [el('span', { text: 'Attempts ' }), String(s.attempts || 0)]),
        ]),
      ]);
      if (s.error) li.append(el('span', { class: 'step-err', text: s.error }));
      return li;
    }));
    return { done, total: steps.length, pct, status: ex ? ex.status : 'NONE' };
  }

  function totals(kpi4) {
    const sum = (f) => kpi4.reduce((a, r) => a + num(r[f] || 0), 0);
    const rev = Math.round(sum('billed_amount') * 100) / 100;
    const enc = sum('eligible_encounters');
    return { rev, enc, avg: enc ? rev / enc : NaN, patients: sum('patients_with_eligible_encounters'), registered: sum('patients') };
  }

  function renderTiles(t) {
    const tiles = [
      ['Billed revenue (INR, excl. tax)', '₹' + inr(t.rev), lakh(t.rev) + ' · Jan–Jun 2026'],
      ['Eligible encounters', int(t.enc), 'Completed, discharged by the cutoff'],
      ['Average bill per encounter', '₹' + inr(t.avg), 'Revenue ÷ eligible encounters'],
      ['Patients billed', int(t.patients), `of ${int(t.registered)} valid patients`],
    ];
    $('#tiles').replaceChildren(...tiles.map(([l, v, s]) => el('div', { class: 'card tile' }, [
      el('span', { class: 'tile-label', text: l }), el('span', { class: 'tile-value', text: v }), el('span', { class: 'tile-sub', text: s }),
    ])));
  }

  function renderAudit(rows) {
    const tb = $('#audit-table tbody');
    if (!rows.length) { tb.replaceChildren(el('tr', null, [el('td', { class: 'empty', colspan: '6', text: 'No audit rows exported.' })])); return; }
    tb.replaceChildren(...rows.map((r) => {
      const ok = num(r.rows_read) === num(r.rows_accepted) + num(r.rows_rejected);
      return el('tr', null, [
        el('td', { text: r.source_file }),
        el('td', { class: 'num', text: int(r.rows_read) }),
        el('td', { class: 'num', text: int(r.rows_accepted) }),
        el('td', { class: 'num' + (num(r.rows_rejected) > 0 ? ' bad' : ''), text: int(r.rows_rejected) }),
        el('td', { class: 'num', text: (num(r.rows_accepted) / num(r.rows_read) * 100).toFixed(1) }),
        el('td', null, [el('span', { class: 'pill ' + (ok ? 'ok' : 'bad'), text: ok ? 'read = accepted + rejected' : 'does not balance' })]),
      ]);
    }));
  }

  function renderTable(sel, rows, cols) {
    const tb = $(sel + ' tbody');
    if (!rows.length) { tb.replaceChildren(el('tr', null, [el('td', { class: 'empty', colspan: String(cols.length), text: 'No rows.' })])); return; }
    tb.replaceChildren(...rows.map((r) => el('tr', null, cols.map((c) => {
      if (typeof c === 'function') return c(r);
      const [field, kind] = c;
      return el('td', { class: kind ? 'num' : '', text: kind === 'inr' ? inr(r[field]) : kind === 'int' ? int(r[field]) : r[field] });
    }))));
  }

  function renderChecks(d, t, run) {
    const k = d.kpis || {};
    const exp = d.meta.expected || {};
    const audit = d.audit || [];
    const pii = /name|email|phone|mobile|address/i;
    const kpiCols = Object.values(k).flatMap((rows) => (rows[0] ? Object.keys(rows[0]) : []));
    const leaked = kpiCols.filter((c) => pii.test(c) && c !== 'hospital_name');
    const resOk = (d.resources || []).filter((r) => r.status === 'Active').length;
    const resAll = (d.resources || []).length;
    const balanced = audit.length > 0 && audit.every((r) => num(r.rows_read) === num(r.rows_accepted) + num(r.rows_rejected));
    const revMatch = Math.abs(t.rev - exp.billed_revenue) < 0.005 && t.enc === exp.eligible_encounters;
    const kpiCount = Object.values(k).filter((rows) => rows.length > 0).length;
    const retries = (d.pipeline.steps || []).filter((s) => s.attempts > 1).length;
    const st = (cond, waiting) => (waiting ? 'wait' : cond ? 'pass' : 'fail');
    const running = run.status === 'RUNNING';
    const checks = [
      ['Workflow finished on AWS', st(run.status === 'SUCCEEDED', running),
        running ? `Running: ${run.done} of ${run.total} steps done` : `Step Functions status: ${run.status}`],
      ['Four ordered tasks, one retry each', st(run.total === 4 && run.done === 4, running),
        `landing → bronze → silver → gold; ${run.done}/4 succeeded` + (retries ? `, ${retries} needed its retry` : ', none needed a retry')],
      ['Audit balances for every file', st(balanced, !audit.length),
        audit.length ? `rows read = accepted + rejected in ${audit.filter((r) => num(r.rows_read) === num(r.rows_accepted) + num(r.rows_rejected)).length} of ${audit.length} files` : 'Audit not exported yet'],
      ['AWS result matches the local run', st(revMatch, !t.enc),
        `₹${inr(t.rev)} over ${int(t.enc)} encounters; local run gave ₹${inr(exp.billed_revenue)} over ${int(exp.eligible_encounters)}`],
      ['Four required KPIs + two stretch KPIs', st(kpiCount === 6, false), `${kpiCount} of 6 KPI tables have rows`],
      ['No personal data in KPI output', st(leaked.length === 0, !kpiCols.length),
        leaked.length ? 'Found columns: ' + leaked.join(', ') : 'No name, email, phone or address columns in any KPI table'],
      ['All AWS resources in place', st(resOk === resAll && resAll > 0, !resAll), `${resOk} of ${resAll} resources active`],
    ];
    const mark = { pass: '✓', fail: '✕', wait: '…' };
    $('#check-list').replaceChildren(...checks.map(([title, s, detail]) => el('li', { class: 'check ' + s }, [
      el('span', { class: 'check-mark', 'aria-label': s === 'pass' ? 'Passed' : s === 'fail' ? 'Failed' : 'Waiting', text: mark[s] }),
      el('span', { class: 'check-title', text: title }),
      el('span', { class: 'check-detail', text: detail }),
    ])));
    return checks.filter((c) => c[1] === 'pass').length + ' of ' + checks.length;
  }

  function render(d) {
    const k = d.kpis || {};
    const run = renderPipeline(d.pipeline || {});
    const t = totals(k.kpi4_patient_category_profile || []);
    const rejected = (d.audit || []).reduce((a, r) => a + num(r.rows_rejected), 0);
    const passed = renderChecks(d, t, run);

    const lede = $('#lede');
    lede.replaceChildren(
      'The AWS pipeline is ', el('b', { text: run.pct + '% complete' }), ` (${run.done} of ${run.total} steps). `,
      'Batch ', el('b', { text: d.meta.batch_id }), ' billed ', el('b', { text: '₹' + inr(t.rev) }),
      ' across ', el('b', { text: int(t.enc) }), ' eligible encounters',
      (d.audit || []).length ? ', after ' : '.', (d.audit || []).length ? el('b', { text: int(rejected) }) : '',
      (d.audit || []).length ? ' bad rows were quarantined. ' : ' ',
      el('b', { text: passed }), ' evaluation checks pass.',
    );
    const facts = [['Region', d.meta.region], ['Account', d.meta.account], ['Data cutoff', d.meta.cutoff], ['Exported', fmtTime(d.meta.generated_at)]];
    $('#facts').replaceChildren(...facts.map(([a, b]) => el('div', null, [el('dt', { text: a }), el('dd', { text: b })])));

    if ((d.warnings || []).length) { const b = $('#banner'); b.textContent = d.warnings.join(' '); b.hidden = false; }

    renderTiles(t);
    renderAudit(d.audit || []);

    const kpi2 = k.kpi2_hospital_encounter_type || [];
    const maxAvg = Math.max(1, ...kpi2.map((r) => num(r.average_bill)));
    const names = Object.fromEntries((k.kpi5_inpatient_length_of_stay || []).map((r) => [r.hospital_id, r.hospital_name]));

    const draw = () => {
      stackedMonthly($('#kpi1-chart'), k.kpi1_revenue_by_department_month || []);
      hbars($('#kpi3-chart'), (k.kpi3_top10_patients || []).slice().sort((a, b) => num(a.rank) - num(b.rank))
        .map((r) => ({ name: r.patient_id, v: num(r.billed_amount), rank: r.rank, enc: r.eligible_encounters })), {
        label: 'Ten patients with the highest billed amount',
        fmt: (v) => '₹' + inr(v), tick: (v) => '₹' + (v / 1000) + 'k',
        tip: (r) => ['#' + r.rank + ' ' + r.name, '₹' + inr(r.v), r.enc + ' eligible encounters'],
      });
      hbars($('#kpi5-chart'), (k.kpi5_inpatient_length_of_stay || []).map((r) => ({
        name: r.hospital_name, v: num(r.avg_length_of_stay_days), max: num(r.max_length_of_stay_days), n: r.inpatient_encounters, id: r.hospital_id,
      })), {
        label: 'Average and longest inpatient stay per hospital, in days',
        fmt: (v) => v.toFixed(2) + ' d', tick: (v) => v + ' d',
        tip: (r) => [r.name + ' (' + r.id + ')', 'Average ' + r.v.toFixed(2) + ' days', 'Longest ' + r.max.toFixed(2) + ' days', r.n + ' inpatient encounters'],
      });
      regionMix($('#kpi6-chart'), k.kpi6_region_service_category_mix || []);
      groupedBars($('#kpi2-chart'), k.kpi2_hospital_encounter_type || [], names);
      hbars($('#kpi4-chart'), (k.kpi4_patient_category_profile || []).map((r) => ({
        name: r.patient_category, v: num(r.billed_amount), avg: r.average_bill, enc: r.eligible_encounters, pat: r.patients_with_eligible_encounters,
      })), {
        label: 'Billed amount per patient category',
        fmt: (v) => lakh(v), tick: (v) => (v / 100000) + ' L',
        tip: (r) => [r.name, 'Billed ₹' + inr(r.v), r.enc + ' eligible encounters, ' + r.pat + ' patients', 'Average bill ₹' + inr(r.avg)],
      });
    };
    draw();
    let w = window.innerWidth;
    window.addEventListener('resize', () => { if (Math.abs(window.innerWidth - w) > 20) { w = window.innerWidth; draw(); } });

    renderTable('#kpi2-table', kpi2, [
      (r) => el('td', { text: names[r.hospital_id] ? `${r.hospital_id} · ${names[r.hospital_id].replace('CareVista ', '')}` : r.hospital_id }),
      ['encounter_type'], ['eligible_encounters', 'int'], ['billed_amount', 'inr'], ['average_bill', 'inr'],
      (r) => { const b = el('div', { class: 'minibar' }); b.style.width = (num(r.average_bill) / maxAvg * 100).toFixed(1) + '%'; return el('td', { class: 'bar-col' }, [b]); },
    ]);
    renderTable('#kpi4-table', k.kpi4_patient_category_profile || [], [
      ['patient_category'], ['patients', 'int'], ['patients_with_eligible_encounters', 'int'], ['eligible_encounters', 'int'], ['billed_amount', 'inr'], ['average_bill', 'inr'],
    ]);
    renderTable('#res-table', d.resources || [], [
      ['service'], (r) => el('td', null, [el('code', { text: r.name })]), (r) => el('td', { class: 'wrap', text: r.purpose }),
      (r) => el('td', null, [el('span', { class: 'pill ' + (r.status === 'Active' ? 'ok' : 'bad'), text: r.status })]),
    ]);

    const files = [
      ['kpi_report.html', 'Full KPI report (HTML)'], ['kpi_report.md', 'Full KPI report (Markdown)'],
      ...Object.keys(k).map((n) => [n + '.csv', n.replace(/^kpi(\d)_/, 'KPI $1 · ').replace(/_/g, ' ') + ' (CSV)']),
    ];
    $('#download-list').replaceChildren(...files.map(([f, label]) => el('li', null, [el('a', { href: 'data/csv/' + f, target: '_blank', rel: 'noopener', text: label })])));
    $('#foot').textContent = `Source: ${d.meta.lake} (gold and audit Delta tables) and the Step Functions execution history, exported ${fmtTime(d.meta.generated_at)}. Refresh with: python deploy/aws/export_results.py`;
  }

  fetch('data/results.json', { cache: 'no-store' })
    .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(render)
    .catch((err) => {
      $('#lede').textContent = 'No results to show yet.';
      const b = $('#banner');
      b.textContent = `Could not read data/results.json (${err.message}). Run "python deploy/aws/export_results.py" after the pipeline finishes, then reload. Open this page through the local server (scripts/start_frontend), not by double-clicking the file.`;
      b.hidden = false;
    });
})();
