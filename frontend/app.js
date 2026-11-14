// TrendTrace simple frontend: plain JavaScript, no build step, no external libraries.
"use strict";
const API = "/api/v1";
const $ = (sel) => document.querySelector(sel);

// ---------- helpers ----------
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) node.append(c instanceof Node ? c : document.createTextNode(String(c ?? "")));
  return node;
}

async function call(path, body) {
  const res = await fetch(API + path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const json = await res.json();
  if (json.error) throw new Error(`${json.error.message} (${json.error.code})`);
  if (json.data_status === "mock") $("#mock-banner").hidden = false;
  return json;
}

function show(target, ...nodes) { target.replaceChildren(...nodes); }
function loading(target) { show(target, el("p", { class: "muted" }, "Working… (the free server may take up to a minute to wake up)")); }
function fail(target, err) { show(target, el("p", { class: "error" }, err.message)); }
const fmt = (v, d = 3) => (v === null || v === undefined ? "n/a" : Number(v).toPrecision(d));
const perDecade = (u) => (u === "1 per decade" || u === "1" ? "per decade" : u);
const pText = (p) => (p < 0.001 ? "< 0.001" : p.toFixed(3));

// ---------- tiny SVG chart: points, fitted line, uncertainty band ----------
function chart(fit, yLabel) {
  const W = 900, H = 330, L = 60, R = 15, T = 30, B = 35;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const add = (name, attrs) => { const n = document.createElementNS(NS, name); for (const k in attrs) n.setAttribute(k, attrs[k]); svg.append(n); return n; };
  const t = fit.map((f) => new Date(f.date).getTime());
  const ys = fit.flatMap((f) => [f.analysed, f.fitted, f.lower, f.upper]).filter((v) => v !== null);
  const [t0, t1] = [Math.min(...t), Math.max(...t)];
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const pad = (y1 - y0) * 0.08 || 1; y0 -= pad; y1 += pad;
  const X = (v) => L + ((v - t0) / (t1 - t0 || 1)) * (W - L - R);
  const Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  // axes and gridlines
  for (let i = 0; i <= 4; i++) {
    const v = y0 + ((y1 - y0) * i) / 4;
    add("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: "#eee" });
    add("text", { x: L - 6, y: Y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "#666" }).textContent = fmt(v, 3);
  }
  const years = [...new Set(fit.map((f) => f.date.slice(0, 4)))];
  const step = Math.ceil(years.length / 10);
  years.forEach((yr, i) => {
    if (i % step) return;
    add("text", { x: X(new Date(`${yr}-07-01`).getTime()), y: H - 12, "text-anchor": "middle", "font-size": 11, fill: "#666" }).textContent = yr;
  });
  add("text", { x: 12, y: 14, "font-size": 12, fill: "#444" }).textContent = yLabel;
  const hasTrend = fit[0].fitted !== null && fit[0].fitted !== undefined;
  // band
  if (hasTrend) {
  const upper = fit.map((f, i) => `${X(t[i])},${Y(f.upper)}`);
  const lower = fit.map((f, i) => `${X(t[i])},${Y(f.lower)}`).reverse();
  add("polygon", { points: [...upper, ...lower].join(" "), fill: "rgba(214,69,47,.18)" });
  }
  // data points (connected thinly) and fitted line
  add("polyline", { points: fit.map((f, i) => `${X(t[i])},${Y(f.analysed)}`).join(" "), fill: "none", stroke: "#9cbbe0", "stroke-width": 1 });
  fit.forEach((f, i) => add("circle", { cx: X(t[i]), cy: Y(f.analysed), r: fit.length > 60 ? 2 : 3.5, fill: "#0b5fae" }));
  if (hasTrend) add("line", { x1: X(t[0]), y1: Y(fit[0].fitted), x2: X(t[t.length - 1]), y2: Y(fit[fit.length - 1].fitted), stroke: "#d6452f", "stroke-width": 2.5 });
  return el("div", {}, svg, el("div", { class: "legend" },
    el("span", {}, el("i", { class: "dot" }), " data"), el("span", {}, el("i", { class: "line" }), " Theil–Sen trend"),
    el("span", {}, el("i", { class: "band" }), " likely range of the trend")));
}

function statsTable(rows) {
  return el("table", {}, rows.map(([k, v]) => el("tr", {}, el("th", {}, k), el("td", {}, v))));
}

function verdict(sig) { return el("span", { class: sig ? "sig" : "nosig" }, sig ? "Statistically significant" : "Not statistically significant"); }

// ---------- tabs ----------
document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => openTab(b.dataset.tab)));
function openTab(name) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll("main section").forEach((s) => (s.hidden = s.id !== `tab-${name}`));
}

// ---------- Analyze ----------
let regions = [], variables = [], catalog = [];
async function loadMeta() {
  try {
    const [r, v, cat, res] = await Promise.all([call("/regions"), call("/variables"), call("/catalog"), call("/research/series")]);
    regions = r.result.regions; variables = v.result; catalog = cat.result.variables;
    $("#region").replaceChildren(...regions.map((x) => el("option", { value: x.region_id }, x.name)));
    $("#more-region").replaceChildren(...regions.map((x) => el("option", { value: x.region_id }, x.name)));
    fillVariables();
    $("#region").addEventListener("change", fillVariables);
    $("#variable").addEventListener("change", describeVariable);
    for (const [k, label] of Object.entries(cat.result.themes)) $("#theme").append(el("option", { value: k }, `${k} — ${label}`));
    for (const [k, label] of Object.entries(cat.result.place_types)) $("#place").append(el("option", { value: k }, label));
    $("#research").replaceChildren(...res.result.series.map((s) => el("option", { value: s.research_id }, `${s.region_id}: ${s.label} (${s.unit})`)));
  } catch (e) { fail($("#analyze-out"), e); }
}
function fillVariables() {
  const region = regions.find((r) => r.region_id === $("#region").value);
  $("#variable").replaceChildren(...region.variables.map((v) => el("option", { value: v }, variables.find((x) => x.variable === v)?.label || v)));
  describeVariable();
}
function describeVariable() {
  const id = $("#variable").value;
  const c = catalog.find((x) => x.id === id), v = variables.find((x) => x.variable === id);
  $("#variable-info").textContent = c ? `${c.name}: ${c.plain_definition} Caveat: ${c.caveat}` : (v ? v.description : "");
}

$("#analyze-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target), out = $("#analyze-out");
  const body = { region_id: f.get("region_id"), variable: f.get("variable"), season: f.get("season"),
                 options: { alpha: Number(f.get("alpha")) } };
  if (f.get("start")) body.start = f.get("start");
  if (f.get("end")) body.end = f.get("end");
  loading(out);
  try {
    const { result } = await call("/analyze/detail", body);
    const tr = result.trend, a = result.analysis;
    const explainBox = el("p", { class: "muted" });
    const csv = `${API}/export/csv?region_id=${encodeURIComponent(tr.region_id)}&variable=${encodeURIComponent(tr.variable)}`;
    show(out,
      el("div", { class: "card" }, verdict(tr.significant), el("p", { class: "summary" }, result.plain_language)),
      el("div", { class: "card" }, chart(a.fit, tr.season === "all" ? `${tr.variable} anomaly${tr.slope_unit.startsWith("1 ") ? "" : " (" + tr.slope_unit.replace(" per decade", "") + ")"}` : `${tr.season} mean`)),
      el("div", { class: "card" }, statsTable([
        ["Theil–Sen slope", `${fmt(tr.sen_slope)} ${perDecade(tr.slope_unit)} (range ${fmt(tr.slope_ci[0])} to ${fmt(tr.slope_ci[1])})`],
        ["Change per decade", `${tr.percent_change_per_decade.toFixed(1)}%`],
        ["Mann–Kendall p (Hamed–Rao)", pText(tr.p_value)],
        ["OLS t-test slope", `${fmt(tr.ols_slope)} (range ${fmt(tr.ols_ci[0])} to ${fmt(tr.ols_ci[1])})`],
        ["Evidence label (team rule)", tr.evidence.evidence_label],
        ["Valid observations", `${tr.n_valid} of ${tr.n_expected} (${tr.evidence.valid_obs_pct.toFixed(1)}%)`],
        ["Years needed to detect", a.detection.years_needed === null ? "n/a" : `~${Math.round(a.detection.years_needed)} (have ${Math.round(a.detection.years_available)})`],
        ["Step change (Pettitt)", a.change_point.significant ? `around ${a.change_point.date.slice(0, 7)}` : "none detected"],
      ]), el("p", {}, el("button", { class: "btn", onclick: async () => {
          explainBox.textContent = "Explaining…";
          try { const ex = await call("/explain", { result_type: "trend", result_id: tr.result_id });
                explainBox.textContent = `${ex.result.source === "llm" ? "AI-generated explanation of computed results" : "Automatic summary"}: ${ex.result.text}`; }
          catch (err) { explainBox.textContent = err.message; }
        } }, "Explain"), " ", el("a", { href: csv }, "Download series CSV")), explainBox,
        el("p", { class: "muted" }, tr.limitations.join(" "))));
  } catch (err) { fail(out, err); }
});

// ---------- Scan ----------
$("#scan-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#scan-out"); loading(out);
  try {
    const { result } = await call(`/scan?season=${new FormData(e.target).get("season")}`);
    show(out,
      el("p", { class: "summary" }, result.summary),
      ...result.opposite_directions.map((c) => el("div", { class: "card" },
        el("b", {}, `Opposite trends for ${c.variable}: `), `up in ${c.increasing_in.join(", ")}; down in ${c.decreasing_in.join(", ")}.`)),
      el("table", {}, el("tr", {}, ["Region", "Variable", "Slope / decade", "% / decade", "p", "q (FDR)", "Result"].map((h) => el("th", {}, h))),
        result.rows.map((r) => el("tr", {}, el("td", {}, r.region_name), el("td", {}, r.variable),
          el("td", {}, `${fmt(r.sen_slope)} ${r.slope_unit.startsWith("1 ") ? "" : r.slope_unit.replace(" per decade", "")}`), el("td", {}, `${r.percent_change_per_decade.toFixed(1)}%`),
          el("td", {}, pText(r.p_value)), el("td", {}, pText(r.q_value)),
          el("td", {}, el("span", { class: r.status === "significant" ? "sig" : "nosig" }, r.status.replaceAll("_", " ")))))),
      el("p", { class: "muted" }, "q-values correct for testing many series at once (Benjamini–Hochberg)."));
  } catch (err) { fail(out, err); }
});

// ---------- Discover ----------
$("#discover-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target), out = $("#discover-out");
  const body = {};
  for (const k of ["theme", "place_type", "question"]) if (f.get(k)) body[k] = f.get(k);
  loading(out);
  try {
    const { result } = await call("/discover", body);
    show(out, ...result.suggestions.map((s) => el("div", { class: "card" },
      el("h3", {}, `${s.name} `, el("span", { class: "muted" }, `${s.mission} · ${s.unit}`)),
      el("p", {}, s.plain_definition), el("p", {}, el("b", {}, "Why it trends: "), s.why_trends),
      el("p", { class: "muted" }, "Suggested because: " + s.reasons.join(" ")),
      el("p", { class: "muted" }, "Caveat: " + s.caveat),
      s.available_now
        ? el("button", { class: "btn", onclick: () => { $("#variable").value = s.variable_id; describeVariable(); openTab("analyze"); } }, "Analyze now")
        : el("p", {}, el("b", {}, "Get the data: "), s.next_step.how))),
      ...(result.region_suggestions.length ? [el("p", { class: "muted" }, "Example regions: " +
        result.region_suggestions.map((r) => `${r.name} [${r.bbox.join(", ")}]`).join("; "))] : []));
  } catch (err) { fail(out, err); }
});

// ---------- Real data + upload ----------
function seriesResult(r) {
  return [
    el("div", { class: "card" }, verdict(r.significant), el("p", { class: "summary" }, r.plain_language)),
    el("div", { class: "card" }, chart(r.fit, `${r.label} (${r.unit})`)),
    el("div", { class: "card" }, statsTable([
      ["Theil–Sen slope", `${fmt(r.sen_slope_per_decade)} ${perDecade(r.unit + " per decade")} (range ${fmt(r.sen_ci_per_decade[0])} to ${fmt(r.sen_ci_per_decade[1])})`],
      ["Mann–Kendall p (Hamed–Rao)", pText(r.mk_p_value)],
      ["OLS t-test p", pText(r.ols_p_value)],
      ["Years needed to detect", r.significant ? "already detected" : (r.detection.years_needed === null ? "n/a" : `~${Math.round(r.detection.years_needed)} (have ${Math.round(r.detection.years_available)})`)],
      ["Data source", r.input_provenance.origin || r.input_provenance.title || r.input_origin],
    ])),
  ];
}
$("#real-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#real-out"); loading(out);
  try { show(out, ...seriesResult((await call("/analyze/series", { research_id: $("#research").value })).result)); }
  catch (err) { fail(out, err); }
});
$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#real-out"), file = $("#csv-file").files[0], f = new FormData(e.target);
  if (!file) return fail(out, new Error("Choose a CSV file first."));
  loading(out);
  try {
    const body = { giovanni_csv: await file.text(), conversion: f.get("conversion") };
    if (f.get("place")) body.place = f.get("place");
    show(out, ...seriesResult((await call("/analyze/series", body)).result));
  } catch (err) { fail(out, err); }
});

// ---------- Unusual months, indicators, interaction ----------
$("#more-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target), out = $("#more-out"), rid = f.get("region_id"), what = f.get("what");
  loading(out);
  try {
    if (what === "anomalies") {
      const { result } = await call(`/anomalies?region_id=${rid}&variable=both`);
      const cards = result.results.map((r) => {
        const flagged = r.anomalies.filter((a) => a.category);
        return el("div", { class: "card" },
          el("h3", {}, r.variable === "aod" ? "AOD (haze)" : "Rainfall", " ",
             el("span", { class: "muted" }, `${flagged.length} unusual of ${r.anomalies.length} months; same-calendar-month baseline ${r.baseline.start} to ${r.baseline.end}`)),
          el("table", {}, el("tr", {}, ["Month", "Value", "Usual (median)", "Flag", "Note"].map((h) => el("th", {}, h))),
            flagged.map((a) => el("tr", {}, el("td", {}, a.date.slice(0, 7)), el("td", {}, fmt(a.value)),
              el("td", {}, fmt(a.baseline_median)), el("td", {}, a.category.replaceAll("_", " ")), el("td", {}, a.note)))));
      });
      const both = result.combined_flags.length
        ? el("div", { class: "card" }, el("b", {}, "Months unusual in both: "),
            result.combined_flags.map((c) => `${c.date.slice(0, 7)} (${c.category.replaceAll("_", " ")})`).join(", "),
            el("p", { class: "muted" }, "Co-occurrence only; it does not show that one caused the other."))
        : el("p", { class: "muted" }, "No month was unusual in both rainfall and AOD.");
      show(out, both, ...cards);
    } else if (what === "interaction") {
      const season = f.get("season") === "annual" ? "all" : f.get("season");
      const { result: r } = await call(`/interaction?region_id=${rid}&season=${season}`);
      const sig = r.p_value !== null && r.p_value < 0.05;
      show(out, el("div", { class: "card" },
        el("p", { class: "summary" }, `${r.n_events_used} heavy-rain days (top 10% of ${season === "all" ? "all" : season} days) had haze measured before and after. `
          + `Median AOD change from 3 days before to 3 days after: ${fmt(r.median_change)} (likely range ${fmt(r.median_change_ci?.[0])} to ${fmt(r.median_change_ci?.[1])}). `
          + (r.p_value === null ? r.note : `Wilcoxon p = ${pText(r.p_value)}: ${sig ? "a consistent change" : "no consistent change"}. `)
          + `Ordinary days in the same months changed by ${fmt(r.control.median_change)}.`),
        statsTable([["Events found / used", `${r.n_events} / ${r.n_events_used}`],
                    ["Valid AOD days before / after", `${r.valid_aod_pct_before}% / ${r.valid_aod_pct_after}%`],
                    ["Monthly rain–haze correlation (Spearman, seasons removed)", `rho = ${fmt(r.monthly_association.rho)}, p = ${pText(r.monthly_association.p_value)}, n = ${r.monthly_association.n}`]]),
        el("p", { class: "muted" }, r.guardrail)));
    } else {
      const { result: r } = await call(`/rainfall/indicators?region_id=${rid}&indicator=${what}&season=${f.get("season")}`);
      const fit = r.values.filter((v) => v.value !== null).map((v) => ({ date: `${v.year}-07-01`, analysed: v.value, fitted: null, lower: null, upper: null }));
      if (r.trend) {
        const t = r.trend, mid = fit.reduce((s, p) => s + p.analysed, 0) / fit.length, ym = 2013.5;
        for (const p of fit) {
          const dy = (Number(p.date.slice(0, 4)) - ym) / 10;
          p.fitted = mid + t.sen_slope * dy; p.lower = mid + Math.min(t.slope_ci[0] * dy, t.slope_ci[1] * dy); p.upper = mid + Math.max(t.slope_ci[0] * dy, t.slope_ci[1] * dy);
        }
      }
      const t = r.trend;
      show(out,
        el("div", { class: "card" }, t ? verdict(t.significant) : "", el("p", { class: "summary" },
          t ? `Trend: ${fmt(t.sen_slope)} ${t.slope_unit} (range ${fmt(t.slope_ci[0])} to ${fmt(t.slope_ci[1])}), Mann–Kendall p = ${pText(t.p_value)}.` : r.trend_note),
          el("p", { class: "muted" }, r.definition)),
        el("div", { class: "card" }, chart(fit, `${what.replaceAll("_", " ")} (${r.unit})`)));
    }
  } catch (err) { fail(out, err); }
});

// ---------- Demos ----------
async function loadDemos() {
  const out = $("#demos-out");
  try {
    const { result } = await call("/demos");
    show(out, ...result.map((d) => {
      const log = el("div");
      return el("div", { class: "card" },
        el("h3", {}, d.title, " ", el("span", { class: "muted" }, `[${d.data} data]`)),
        el("p", {}, el("b", {}, "Question: "), d.question),
        el("button", { class: "btn", onclick: () => playDemo(d, log) }, "Play demo"), log);
    }));
  } catch (err) { fail(out, err); }
}
async function playDemo(demo, log) {
  log.replaceChildren();
  for (const [i, s] of demo.steps.entries()) {
    log.append(el("p", {}, el("b", {}, `Step ${i + 1}. `), s.narration));
    if (!s.method) continue;
    try {
      const path = s.path.replace(API, "");
      const { result } = s.method === "POST" ? await call(path, s.body) : await call(path);
      const text = result.plain_language || result.summary ||
        (result.suggestions && result.suggestions.slice(0, 3).map((x) => x.name).join(", ")) ||
        (result.questions && result.questions.map((q) => q.question).join(" ")) || "Done.";
      log.append(el("p", { class: "summary" }, text));
    } catch (err) { log.append(el("p", { class: "error" }, err.message)); }
  }
  log.append(el("p", { class: "muted" }, "What to notice: " + demo.what_to_notice));
}

// Show a first result straight away so the page is never empty.
loadMeta().then(() => {
  if ([...$("#variable").options].some((o) => o.value === "aod")) { $("#variable").value = "aod"; describeVariable(); }
  if ($("#region").options.length) $("#analyze-form").requestSubmit();
  // Deep links such as #more=interaction open that view directly (handy for demos).
  const m = location.hash.match(/^#more=(\w+)/);
  if (m) { $("#more-form").elements.what.value = m[1]; openTab("more"); $("#more-form").requestSubmit(); }
});
loadDemos();
