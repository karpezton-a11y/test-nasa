// Guided UX for the challenge audience (students and the scientifically curious public):
// 1) a 3-question "data detective" flow -> /api/v1/discover -> plain definitions -> live trend test,
// 2) watchable demos that run the real engine step by step, 3) a glossary with tap-to-explain terms.
const API = "/api/v1";
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const THEME_ICON = {
  air: '<path d="M6 14h22a5 5 0 1 0-5-5M6 20h30a5 5 0 1 1-5 5M6 26h14"/>',
  heat: '<path d="M20 6a4 4 0 0 1 4 4v14a7 7 0 1 1-8 0V10a4 4 0 0 1 4-4z"/><path d="M20 16v12"/>',
  water: '<path d="M20 6c6 8 10 13 10 18a10 10 0 0 1-20 0c0-5 4-10 10-18z"/>',
  land: '<path d="M20 34V18"/><path d="M20 22c-8 0-12-6-12-12 8 0 12 5 12 12zM20 18c0-7 4-12 12-12 0 7-4 12-12 12z"/>',
  ice: '<path d="M20 4v32M6 12l28 16M6 28l28-16M16 6l4 4 4-4M16 34l4-4 4 4"/>',
  ocean: '<path d="M4 16c4-4 8-4 12 0s8 4 12 0 6-3 8-2M4 24c4-4 8-4 12 0s8 4 12 0 6-3 8-2M4 32c4-4 8-4 12 0s8 4 12 0 6-3 8-2"/>',
};
const THEMES = [
  ["air", "Air", "Haze, smoke, pollution gases and ozone"], ["heat", "Heat", "Air and surface temperature"],
  ["water", "Water", "Rain, soil water, evaporation, rivers"], ["land", "Land", "Plants, forests, fires, land surface"],
  ["ice", "Ice", "Snow and frozen water"], ["ocean", "Ocean", "Sea surface and ocean colour"],
];
const PLACE_ICON = {
  city: '<path d="M5 35V18h8v17M13 35V8h10v27M23 35V14h12v21M8 22h2M8 27h2M16 13h4M16 18h4M16 23h4M27 19h4M27 24h4"/>',
  farmland: '<path d="M4 30c8-6 24-6 32 0M4 24c8-6 24-6 32 0M20 4v10M15 9l5-5 5 5"/>',
  desert: '<circle cx="28" cy="11" r="5"/><path d="M3 32c6-8 12-8 18 0M17 32c6-6 13-7 20 0"/>',
  rainforest: '<path d="M12 35V24M28 35V22M12 24c-7 0-8-9-2-11 0-6 9-7 10-1 6 0 6 10-1 12h-7zM28 22c-6 0-7-8-1-10 1-5 8-5 9 0 5 1 4 10-2 10h-6z"/>',
  coast_estuary: '<path d="M4 14c4-3 8-3 12 0s8 3 12 0 6-2 8-1M4 22c4-3 8-3 12 0M20 22l4 13M20 22l-6 13M20 22l12 9"/>',
  mountain_snow: '<path d="M3 34l12-20 7 11 5-7 10 16zM15 14l-3 6 3-1 3 2zM27 18l-2 4 2-1 2 1z"/>',
  ocean: '<path d="M4 16c4-4 8-4 12 0s8 4 12 0 6-3 8-2M4 24c4-4 8-4 12 0s8 4 12 0 6-3 8-2M4 32c4-4 8-4 12 0s8 4 12 0 6-3 8-2"/>',
  any: '<circle cx="20" cy="20" r="15"/><path d="M5 20h30M20 5c5 5 5 25 0 30M20 5c-5 5-5 25 0 30"/>',
};
const PLACES = [
  ["city", "Big city", "A large city or industrial area"], ["farmland", "Farmland", "Farming plains and irrigated land"],
  ["desert", "Desert", "Dry desert or semi-arid land"], ["rainforest", "Rain forest", "Tropical rain forest"],
  ["coast_estuary", "Coast & estuary", "Coast, delta or tidal estuary"], ["mountain_snow", "Mountains", "Seasonal snow or glaciers"],
  ["ocean", "Open ocean", "Sea surface and ocean colour"], ["any", "Anywhere", "Show me everything"],
];

export const GLOSSARY = {
  trend: ["Trend", "A steady change over many years, going up or down, once the normal ups and downs are ignored."],
  significant: ["Statistically significant", "The change is too steady to be just random noise. Here that means p is below 0.05: a pattern this strong would turn up by chance less than 1 time in 20."],
  "p-value": ["p-value", "How surprising the data would be if nothing were really changing. Small p (below 0.05) means 'probably a real trend'. Big p means 'could easily be noise'."],
  "theil-sen": ["Theil–Sen slope", "How fast something changes, e.g. +0.08 per decade. It is the middle value of the slopes between every pair of points, so one wild year cannot drag it around."],
  range: ["Likely range", "The band the true rate of change probably sits in (a 95% confidence interval). If it includes zero, we cannot say the trend is real."],
  "mann-kendall": ["Mann–Kendall test", "Checks whether values tend to go up (or down) more often than chance. We use a version that also handles one month being similar to the next."],
  deseason: ["Remove the seasons", "Subtract each month's usual value (every July compared with an average July), so monsoons, winters or fire seasons cannot fake a trend."],
  fdr: ["Many-test check", "When you test many places at once, a few will look significant by luck. The Benjamini–Hochberg check (q-value) corrects for that."],
  anomaly: ["Anomaly", "How far a value is from normal for that time of year. +0.5 °C means half a degree warmer than a usual month like it."],
  detect: ["Years to detect", "How many years of data you would need before a trend of this size stands out from the noise. Short records often can't tell yet."],
  aod: ["Aerosol optical depth (AOD)", "How much sunlight tiny particles (dust, smoke, pollution) block in the whole column of air. 0.1 is clear; above 1 is very hazy. It is not the same as ground-level PM2.5."],
  no2: ["Nitrogen dioxide (NO₂)", "A gas mainly from burning fuel in cars, power plants and factories, measured by satellite as the amount above each square centimetre of ground."],
};

// ---------------------------------------------------------------- shared bits
async function api(path, body) {
  const res = await fetch(API + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const json = await res.json();
  if (json.error) throw new Error(json.error.message);
  return json.result;
}
function sparkline(fit, w = 300, h = 74) {
  const pts = fit.filter((f) => f.analysed !== null && f.analysed !== undefined);
  if (pts.length < 3) return "";
  const ys = pts.flatMap((f) => [f.analysed, f.fitted].filter((v) => v !== null && v !== undefined));
  const y0 = Math.min(...ys), y1 = Math.max(...ys), X = (i) => (i / (pts.length - 1)) * (w - 4) + 2, Y = (v) => h - 4 - ((v - y0) / (y1 - y0 || 1)) * (h - 8);
  // x follows real time, and a missing month or year breaks the line instead of being bridged
  const mo = pts.map((f) => { const [y, m] = f.date.slice(0, 7).split("-").map(Number); return y * 12 + (m || 1); });
  const steps = mo.slice(1).map((v, i) => v - mo[i]).sort((a, b) => a - b), step = steps[Math.floor(steps.length / 2)] || 1;
  const XT = (i) => ((mo[i] - mo[0]) / (mo[mo.length - 1] - mo[0] || 1)) * (w - 4) + 2;
  const segs = [[0]]; for (let i = 1; i < pts.length; i++) { if (mo[i] - mo[i - 1] > step) segs.push([]); segs[segs.length - 1].push(i); }
  const lines = segs.filter((sg) => sg.length > 1).map((sg) => `<polyline points="${sg.map((i) => `${XT(i).toFixed(1)},${Y(pts[i].analysed).toFixed(1)}`).join(" ")}" fill="none" stroke="rgba(124,196,255,.75)" stroke-width="1.3"/>`).join("");
  const hasFit = pts[0].fitted !== null && pts[0].fitted !== undefined;
  const trend = hasFit ? `<line x1="${XT(0)}" y1="${Y(pts[0].fitted)}" x2="${XT(pts.length - 1)}" y2="${Y(pts[pts.length - 1].fitted)}" stroke="#ff7a45" stroke-width="2.5" stroke-linecap="round"/>` : "";
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">${lines}${trend}</svg>`;
}
const verdictPill = (sig) => `<span class="${sig ? "sig" : "nosig"}">${sig ? "Significant trend" : "Not significant"}</span>`;
const term = (key, text) => `<button type="button" class="term" data-term="${key}">${esc(text)}</button>`;
const skeleton = (n = 3) => `<div class="skel-wrap">${'<div class="skel"></div>'.repeat(n)}</div>`;

// ---------------------------------------------------------------- 1) the detective wizard
function initWizard(ctx) {
  const root = $("#wizard"); if (!root) return;
  const state = { theme: "", place_type: "", question: "" };
  const tile = ([key, title, sub], icon, kind) =>
    `<button type="button" class="tile" data-${kind}="${key}"><svg viewBox="0 0 40 40" aria-hidden="true">${icon}</svg><b>${title}</b><small>${sub}</small></button>`;
  $("#wiz-themes").innerHTML = THEMES.map((t) => tile(t, THEME_ICON[t[0]], "theme")).join("");
  $("#wiz-places").innerHTML = PLACES.map((p) => tile(p, PLACE_ICON[p[0]], "place")).join("");

  function go(step) {
    $$(".wiz-panel", root).forEach((p) => p.classList.toggle("active", Number(p.dataset.panel) === step));
    $$(".wiz-steps li", root).forEach((li) => {
      const n = Number(li.dataset.step);
      li.classList.toggle("active", n === step); li.classList.toggle("done", n < step);
    });
    if (step === 3) setTimeout(() => $("#wiz-q").focus({ preventScroll: true }), 250);
  }
  root.addEventListener("click", (e) => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.dataset.theme) { state.theme = t.dataset.theme; mark("#wiz-themes", t); setTimeout(() => go(2), 220); }
    else if (t.dataset.place) { state.place_type = t.dataset.place === "any" ? "" : t.dataset.place; mark("#wiz-places", t); setTimeout(() => go(3), 220); }
    else if ("next" in t.dataset) go(Number(t.closest(".wiz-panel").dataset.panel) + 1);
    else if ("back" in t.dataset) go(Number(t.closest(".wiz-panel").dataset.panel) - 1);
    else if ("restart" in t.dataset) { Object.assign(state, { theme: "", place_type: "", question: "" }); $$(".tile.on", root).forEach((x) => x.classList.remove("on")); $("#wiz-q").value = ""; go(1); }
    else if (t.dataset.example) { $("#wiz-q").value = t.dataset.example; $("#wiz-form").requestSubmit(); }
  });
  function mark(sel, el) { $$(".tile", $(sel)).forEach((x) => x.classList.toggle("on", x === el)); }
  $("#wiz-form").addEventListener("submit", (e) => { e.preventDefault(); state.question = $("#wiz-q").value.trim(); go(4); find(); });

  async function find() {
    const out = $("#wiz-results");
    out.innerHTML = `<p class="muted">Searching NASA variables for clues…</p>${skeleton(3)}`;
    try {
      const body = {}; for (const k of ["theme", "place_type", "question"]) if (state[k]) body[k] = state[k];
      const r = await api("/discover", body);
      const asked = [THEMES.find((t) => t[0] === state.theme)?.[1], PLACES.find((p) => p[0] === state.place_type)?.[1], state.question && `“${state.question}”`].filter(Boolean);
      out.innerHTML = `
        <div class="clue-head"><h3>Your clues</h3><p class="muted">${asked.length ? `For ${asked.map(esc).join(" · ")}` : "Showing the strongest candidates"}${r.matched_keywords?.length ? ` · matched: ${r.matched_keywords.map(esc).join(", ")}` : ""}</p></div>
        <div class="clues">${r.suggestions.slice(0, 4).map(clueCard).join("")}</div>
        ${r.region_suggestions?.length ? `<h4 class="sub-h">Places worth investigating</h4><div class="places">${r.region_suggestions.slice(0, 3).map(placeCard).join("")}</div>` : ""}
        ${r.tips?.length ? `<ul class="tips">${r.tips.map((t) => `<li>💡 ${esc(t)}</li>`).join("")}</ul>` : ""}`;
    } catch (err) { out.innerHTML = `<p class="error">Could not search right now: ${esc(err.message)}. The free server may be waking up; try again in a moment.</p>`; }
  }
  function clueCard(s) {
    const live = s.available_now && s.next_step?.action === "analyze";
    const how = !live && s.next_step?.how ? (s.next_step.how.match(/variable (.+?); download/) || [])[1] : null;
    return `<article class="clue ${live ? "live" : ""}">
      <div class="clue-top"><h4>${esc(s.name)}</h4><span class="badge ${live ? "ok" : ""}">${live ? "● Live now" : "Needs a NASA download"}</span></div>
      <p class="mission mono">${esc(s.mission)}${s.instrument ? " · " + esc(s.instrument) : ""}</p>
      <dl>
        <dt>What it is</dt><dd>${esc(s.plain_definition)}</dd>
        <dt>Why it might change</dt><dd>${esc(s.why_trends)}</dd>
        <dt>Watch out</dt><dd>${esc(s.caveat)}</dd>
      </dl>
      <div class="reasons">${(s.reasons || []).map((x) => `<span>${esc(x)}</span>`).join("")}</div>
      ${live ? `<button class="btn btn-primary btn-small test-btn" type="button" data-region="${esc(s.next_step.body.region_id)}" data-variable="${esc(s.next_step.body.variable)}"><span>Test it for a trend →</span></button><div class="test-out"></div>`
             : `<details class="howto"><summary>How to test it for any place</summary><ol>
                 <li>Open <a href="https://giovanni.gsfc.nasa.gov/giovanni/" target="_blank" rel="noopener">NASA Giovanni</a> and choose “Time Series, Area-Averaged”, monthly.</li>
                 <li>${how ? `Pick <code>${esc(how)}</code> and` : "Pick this variable and"} draw a box around your place.</li>
                 <li>Download the CSV and upload it in the lab: <a href="#lab" data-open-real>Real data &amp; upload</a>.</li></ol></details>`}
    </article>`;
  }
  function placeCard(p) {
    return `<article class="place-card"><h5>${esc(p.name)}</h5><p>${esc(p.why)}</p>
      <button class="btn btn-ghost btn-small" type="button" data-fly="${esc(p.id)}"><span>Fly there on the globe ↑</span></button></article>`;
  }
  $("#wiz-results").addEventListener("click", async (e) => {
    const fly = e.target.closest("[data-fly]");
    if (fly) { ctx.flyTo(fly.dataset.fly); return; }
    if (e.target.closest("[data-open-real]")) { setTimeout(() => document.querySelector('#lab-tabs [data-tab="real"]')?.click(), 400); return; }
    const btn = e.target.closest(".test-btn"); if (!btn) return;
    const box = btn.nextElementSibling;
    btn.disabled = true; box.innerHTML = skeleton(2);
    try {
      const r = await api("/analyze/detail", { region_id: btn.dataset.region, variable: btn.dataset.variable, season: "all" });
      const t = r.trend, pct = /^(degC|C|K) /.test(t.slope_unit) ? "" : ` (${t.percent_change_per_decade >= 0 ? "+" : ""}${t.percent_change_per_decade.toFixed(1)}%)`;
      box.innerHTML = `<div class="test-result">
        <div class="tr-top">${verdictPill(t.significant)}<b>${t.sen_slope >= 0 ? "+" : "−"}${Math.abs(t.sen_slope).toPrecision(3)} ${esc(t.slope_unit.replace("1 per decade", "per decade"))}${pct}</b></div>
        ${sparkline(r.analysis.fit)}
        <p>${esc(r.plain_language)}</p>
        <p class="muted">What that means: ${t.significant ? `the change is steady enough that it is unlikely to be ${term("significant", "just noise")}.` : `the data are too noisy to call this a real ${term("trend", "trend")} yet; see ${term("detect", "years to detect")}.`}</p>
        <button class="btn btn-ghost btn-small" type="button" data-lab="${esc(t.region_id)}|${esc(t.variable)}"><span>Open the full analysis</span></button></div>`;
    } catch (err) { box.innerHTML = `<p class="error">${esc(err.message)}</p>`; }
    finally { btn.disabled = false; }
  });
  $("#wiz-results").addEventListener("click", (e) => { const b = e.target.closest("[data-lab]"); if (b) { const [r, v] = b.dataset.lab.split("|"); ctx.openInLab(r, v); } });
}

// ---------------------------------------------------------------- 2) demo player
function initDemos() {
  const list = $("#demo-list"), player = $("#demo-player"); if (!list) return;
  const ORDER = ["two_cities_no2", "haze_rising", "not_significant_yet", "seasons_matter", "products_disagree", "guided_discovery", "scan_everything"];
  let demos = [], run = 0;
  const load = async () => {
    list.innerHTML = skeleton(4);
    try {
      demos = (await api("/demos")).sort((a, b) => ORDER.indexOf(a.id) - ORDER.indexOf(b.id));
      list.innerHTML = demos.map((d, i) => `<button type="button" role="tab" class="demo-item" data-i="${i}"><span class="mono">0${i + 1}</span><b>${esc(d.title)}</b><small>${d.steps.length} step${d.steps.length === 1 ? "" : "s"} · ${esc(d.data)} data</small></button>`).join("");
    } catch (err) { list.innerHTML = `<p class="error">${esc(err.message)}</p>`; }
  };
  new IntersectionObserver(([e], o) => { if (e.isIntersecting) { load(); o.disconnect(); } }, { rootMargin: "600px" }).observe(list);
  list.addEventListener("click", (e) => { const b = e.target.closest(".demo-item"); if (b) play(Number(b.dataset.i)); });

  function render(result, step) {
    if (!result) return "";
    const lookVar = step.look_at && step.look_at.match(/variables\[id=(\w+)\]\.(\w+)/);
    if (lookVar && result.variables) { const v = result.variables.find((x) => x.id === lookVar[1]); return v ? `<p class="summary"><b>${esc(v.name)}:</b> ${esc(v[lookVar[2]])}</p>` : ""; }
    if (result.rows && result.summary !== undefined) return `<p class="summary">${esc(result.summary)}</p><ul class="demo-rows">${result.rows.slice(0, 5).map((r) => `<li class="${r.status === "significant" ? (r.sen_slope > 0 ? "up" : "down") : "flat"}">${esc(r.headline)}</li>`).join("")}</ul>`;
    if (result.questions) return `<ol class="demo-rows">${result.questions.map((q) => `<li>${esc(q.question)}</li>`).join("")}</ol>`;
    if (result.suggestions) return `<ul class="demo-rows">${result.suggestions.slice(0, 3).map((s) => `<li><b>${esc(s.name)}</b>: ${esc((s.reasons || []).join(" "))}</li>`).join("")}</ul>`;
    const fit = result.analysis?.fit || result.fit;
    const sig = result.trend ? result.trend.significant : result.significant;
    return `<div class="tr-top">${sig === undefined ? "" : verdictPill(sig)}</div>${fit ? sparkline(fit, 560, 110) : ""}<p class="summary">${esc(result.plain_language || result.summary || "Done.")}</p>`;
  }
  async function play(i) {
    const d = demos[i], my = ++run;
    $$(".demo-item", list).forEach((b) => b.classList.toggle("active", Number(b.dataset.i) === i));
    let paused = false, stepIndex = 0, timer = null;
    player.innerHTML = `<div class="dp-head"><span class="mono">Demo 0${i + 1}</span><h3>${esc(d.title)}</h3><p class="muted"><b>Question:</b> ${esc(d.question)}</p></div>
      <ol class="dp-steps">${d.steps.map((_, k) => `<li data-k="${k}"><i></i></li>`).join("")}</ol>
      <div class="dp-stage"><p class="dp-narr"></p><div class="dp-result"></div></div>
      <div class="dp-controls"><button class="btn btn-ghost btn-small" type="button" data-act="toggle"><span>❚❚ Pause</span></button>
        <button class="btn btn-ghost btn-small" type="button" data-act="next"><span>Next step →</span></button>
        <button class="btn btn-ghost btn-small" type="button" data-act="restart"><span>↺ Restart</span></button></div>`;
    player.querySelector(".dp-controls").onclick = (e) => {
      const act = e.target.closest("button")?.dataset.act;
      if (act === "toggle") { paused = !paused; e.target.closest("button").innerHTML = `<span>${paused ? "▶ Play" : "❚❚ Pause"}</span>`; player.classList.toggle("paused", paused); if (!paused) schedule(); else clearTimeout(timer); }
      if (act === "next") { clearTimeout(timer); advance(); }
      if (act === "restart") play(i);
    };
    const schedule = () => { clearTimeout(timer); timer = setTimeout(advance, REDUCED ? 9000 : 6500); };
    async function show(k) {
      if (my !== run) return;
      const s = d.steps[k];
      $$(".dp-steps li", player).forEach((li) => { const n = Number(li.dataset.k); li.classList.toggle("done", n < k); li.classList.toggle("now", n === k); });
      const narr = $(".dp-narr", player), res = $(".dp-result", player);
      narr.textContent = ""; res.innerHTML = s.method ? skeleton(2) : "";
      const text = `Step ${k + 1}. ${s.narration}`;
      if (REDUCED) narr.textContent = text; else { let c = 0; const tt = setInterval(() => { if (my !== run) return clearInterval(tt); narr.textContent = text.slice(0, ++c); if (c >= text.length) clearInterval(tt); }, 14); }
      if (s.method) {
        try { const r = s.method === "POST" ? await api(s.path.replace(API, ""), s.body) : await api(s.path.replace(API, "")); if (my === run) res.innerHTML = render(r, s); }
        catch (err) { if (my === run) res.innerHTML = `<p class="error">${esc(err.message)}</p>`; }
      }
      if (!paused) schedule();
    }
    function advance() {
      if (my !== run) return;
      stepIndex++;
      if (stepIndex < d.steps.length) return show(stepIndex);
      $$(".dp-steps li", player).forEach((li) => { li.classList.remove("now"); li.classList.add("done"); });
      $(".dp-stage", player).insertAdjacentHTML("beforeend", `<div class="dp-notice"><b>What to notice</b><p>${esc(d.what_to_notice)}</p><a class="btn btn-primary btn-small" href="#investigate"><span>Now investigate yourself →</span></a></div>`);
    }
    show(0);
  }
}

// ---------------------------------------------------------------- 3) glossary + tap-to-explain terms
function initGlossary() {
  const grid = $("#gloss-grid");
  if (grid) grid.innerHTML = Object.entries(GLOSSARY).map(([k, [t, d]]) => `<article class="gloss" id="term-${k}"><h3>${esc(t)}</h3><p>${esc(d)}</p></article>`).join("");
  const pop = document.createElement("div"); pop.className = "term-pop"; pop.setAttribute("role", "tooltip"); pop.hidden = true; document.body.append(pop);
  let current = null;
  function open(btn) {
    const g = GLOSSARY[btn.dataset.term]; if (!g) return;
    current = btn; pop.innerHTML = `<b>${esc(g[0])}</b><p>${esc(g[1])}</p>`; pop.hidden = false;
    const r = btn.getBoundingClientRect(), pw = Math.min(320, innerWidth - 24);
    pop.style.width = `${pw}px`;
    const left = Math.max(12, Math.min(innerWidth - pw - 12, r.left + r.width / 2 - pw / 2));
    const top = r.bottom + 10 + pop.offsetHeight > innerHeight ? r.top - pop.offsetHeight - 10 : r.bottom + 10;
    pop.style.transform = `translate(${left}px, ${top}px)`;
    btn.setAttribute("aria-expanded", "true");
  }
  function close() { if (current) current.setAttribute("aria-expanded", "false"); current = null; pop.hidden = true; }
  document.addEventListener("click", (e) => { const b = e.target.closest(".term"); if (b) { e.preventDefault(); b === current ? close() : open(b); } else if (!e.target.closest(".term-pop")) close(); });
  document.addEventListener("pointerover", (e) => { const b = e.target.closest?.(".term"); if (b && matchMedia("(pointer: fine)").matches) open(b); });
  document.addEventListener("pointerout", (e) => { const b = e.target.closest?.(".term"); if (b && b === current && matchMedia("(pointer: fine)").matches) close(); });
  addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  addEventListener("scroll", () => current && close(), { passive: true });
}

export function initGuide(ctx) {
  initWizard(ctx);
  initDemos();
  initGlossary();
}
