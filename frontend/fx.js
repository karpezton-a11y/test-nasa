// TrendTrace motion layer: boot sequence, globe wiring, scroll story, counters, tilt, magnetic buttons.
// Plain ES module, no dependencies besides globe.js. Everything respects prefers-reduced-motion.
import { startRocket } from "/static/rocket.js";
import { startMascot } from "/static/mascot.js";
import { initGuide, THEME_ICON } from "/static/guide.js";

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const FINE = matchMedia("(pointer: fine)").matches;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---------- open the lab on a region + variable ----------
function openInLab(region, variable) {
  window.ttTrack && window.ttTrack("open_lab");
  $("#lab").scrollIntoView({ behavior: REDUCED ? "auto" : "smooth" });
  if (window.ttOpenAnalysis) window.ttOpenAnalysis(region, variable);
}

// ---------- globe ----------
const statusEl = $("#layer-status span");
const LABELS = { aod: "Aerosol haze (MODIS)", no2: "NO₂ (OMI)", air_temperature: "Air temperature (NASA POWER)", rainfall: "Rainfall (GPM IMERG / NASA POWER)" };
const hudLL = $("#hud-ll"), hudAlt = $("#hud-alt"), hudLayer = $("#hud-layer");
let globe = null;
const startGlobe = () => import("/static/globe.js").then(({ createGlobe }) => createGlobe($("#globe-wrap"), {
  layer: "aod",
  onSelect: openInLab,
  onCamera(lat, lon, alt) {
    hudLL.textContent = `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? "N" : "S"} ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? "E" : "W"}`;
    hudAlt.textContent = `${Math.round(alt).toLocaleString("en")} km`;
  },
  onLayer(layer, data, source) {
    $$(".layer-bar .chip").forEach((c) => c.classList.toggle("active", c.dataset.layer === layer));
    hudLayer.textContent = (LABELS[layer] || layer).split(" (")[0].toUpperCase();
    if (!data) return;
    statusEl.textContent = `${source === "live" ? "Live" : "Last computed"} · ${LABELS[layer] || layer} · ${data.summary}`;
    $("#layer-status").classList.toggle("live", source === "live");
  },
})).then((g) => { globe = g; if (activeCase) applyCase(activeCase); })
  .catch(() => { $("#globe-wrap").classList.add("no-webgl"); });
// Let the page paint and become usable first; the 3D globe arrives a moment later.
requestAnimationFrame(() => setTimeout(startGlobe, 60));

$$(".layer-bar .chip").forEach((c) => c.addEventListener("click", () => globe && globe.setLayer(c.dataset.layer)));
$$(".globe-zoom button").forEach((b) => b.addEventListener("click", () => globe && globe.zoom(Number(b.dataset.zoom))));

// ---------- scroll story: each case flies the globe ----------
const cases = $$(".case");
let activeCase = null;
const caseObserver = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    const c = e.target;
    if (c === activeCase) continue;
    activeCase = c;
    cases.forEach((x) => x.classList.toggle("active", x === c));
    runCounters(c);
    applyCase(c);
  }
}, { rootMargin: "-45% 0px -45% 0px" });
function applyCase(c) {
  if (!globe) return;
  globe.setLayer(c.dataset.layer);
  globe.flyTo(Number(c.dataset.lat), Number(c.dataset.lon), Number(c.dataset.dist) || 2.8);
}
cases.forEach((c) => {
  caseObserver.observe(c);
  $(".run", c).addEventListener("click", () => openInLab(c.dataset.region, c.dataset.variable));
});
// Back in the hero: spin again. Below the stage: nothing to do (render loop pauses itself).
new IntersectionObserver(([e]) => {
  if (!globe) return;
  if (e.isIntersecting) {
    activeCase = null; cases.forEach((x) => x.classList.remove("active"));
    if (pendingFocus) { globe.setSpin(false); globe.focusRegion(pendingFocus, 2.8); pendingFocus = null; }
    else { globe.setSpin(true); globe.flyTo(22, 40, 3.4, 1400); }
  }
  else globe.setSpin(false);
}, { threshold: 0.35 }).observe($("#hero"));

// ---------- reveal on scroll ----------
const revealObserver = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); revealObserver.unobserve(e.target); runCounters(e.target); }
}, { threshold: 0.15 });
$$(".reveal, .pipeline, .stat").forEach((n, i) => { n.style.setProperty("--d", `${(i % 6) * 70}ms`); revealObserver.observe(n); });

// ---------- counters ----------
function runCounters(root) {
  const nodes = root.classList?.contains("count") ? [root] : $$(".count", root);
  for (const n of nodes) {
    if (n.dataset.done) continue;
    n.dataset.done = "1";
    const to = Number(n.dataset.to), dec = Number(n.dataset.dec || 0), plus = n.dataset.plus && to > 0 ? "+" : "";
    const fmt = (v) => plus + (v < 0 ? "−" : "") + Math.abs(v).toLocaleString("en", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    if (REDUCED) { n.textContent = fmt(to); continue; }
    const t0 = performance.now(), ms = 1400;
    const step = (now) => { const t = Math.min(1, Math.max(0, (now - t0) / ms)), k = 1 - Math.pow(1 - t, 4);
      n.textContent = fmt(to * k); if (t < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
}

// ---------- headline word scramble (time-based, narrow glyphs so the line never grows) ----------
const scr = $(".scramble");
if (scr && !REDUCED) {
  const words = scr.dataset.words.split("|"), glyphs = "abcdefghijklmnopqrstuvwxyz";
  let wi = 0;
  setInterval(() => {
    wi = (wi + 1) % words.length;
    const target = words[wi], t0 = performance.now(), ms = 700;
    const tick = (now) => {
      const k = Math.min(1, Math.max(0, (now - t0) / ms)), settled = Math.floor(k * target.length);
      let out = target.slice(0, settled);
      for (let i = settled; i < target.length; i++) out += target[i] === " " ? " " : glyphs[(Math.random() * 26) | 0];
      scr.textContent = out;
      if (k < 1) requestAnimationFrame(tick); else scr.textContent = target;
    };
    requestAnimationFrame(tick);
  }, 3400);
}

// ---------- 3D tilt with glare ----------
if (FINE && !REDUCED) {
  $$(".tilt").forEach((card) => {
    card.addEventListener("pointermove", (e) => {
      const r = card.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      card.style.setProperty("--rx", `${(0.5 - y) * 10}deg`); card.style.setProperty("--ry", `${(x - 0.5) * 12}deg`);
      card.style.setProperty("--gx", `${x * 100}%`); card.style.setProperty("--gy", `${y * 100}%`);
    });
    card.addEventListener("pointerleave", () => { card.style.setProperty("--rx", "0deg"); card.style.setProperty("--ry", "0deg"); });
  });

  // ---------- magnetic buttons ----------
  $$(".magnetic").forEach((b) => {
    b.addEventListener("pointermove", (e) => {
      const r = b.getBoundingClientRect();
      b.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.25}px, ${(e.clientY - r.top - r.height / 2) * 0.35}px)`;
    });
    b.addEventListener("pointerleave", () => { b.style.transform = ""; });
  });

  // ---------- cursor glow ----------
  const glow = $(".cursor-glow");
  let gx = innerWidth / 2, gy = innerHeight / 2, cx = gx, cy = gy;
  addEventListener("pointermove", (e) => { gx = e.clientX; gy = e.clientY; glow.classList.add("on"); }, { passive: true });
  const follow = () => { cx += (gx - cx) * 0.12; cy += (gy - cy) * 0.12; glow.style.transform = `translate(${cx}px, ${cy}px)`; requestAnimationFrame(follow); };
  follow();
}

// ---------- top bar ----------
const bar = $(".topbar");
let barState = null;
addEventListener("scroll", () => { const on = scrollY > 30; if (on !== barState) { barState = on; bar.classList.toggle("scrolled", on); } }, { passive: true });

// ---------- lab tab glider ----------
const glider = $(".tab-glider");
function moveGlider() {
  const a = $("#lab-tabs button.active");
  if (!a || !glider) return;
  glider.style.width = `${a.offsetWidth}px`; glider.style.transform = `translateX(${a.offsetLeft}px)`;
}
$$("#lab-tabs button").forEach((b) => b.addEventListener("click", () => requestAnimationFrame(moveGlider)));
new ResizeObserver(moveGlider).observe($("#lab-tabs"));
document.fonts?.ready.then(moveGlider);
new MutationObserver(moveGlider).observe($("#lab-tabs"), { attributes: true, subtree: true, attributeFilter: ["class"] });

// ---------- mission clock ----------
const utc = $("#utc"), met = $("#met"), t0 = Date.now();
const pad = (n) => String(n).padStart(2, "0");
setInterval(() => {
  const d = new Date(), e = Math.floor((Date.now() - t0) / 1000);
  utc.textContent = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
  met.textContent = `T+${pad(Math.floor(e / 3600))}:${pad(Math.floor(e / 60) % 60)}:${pad(e % 60)}`;
}, 1000);

// ---------- climate pulse: warming stripes from the live engine ----------
const API = "/api/v1";
const stripeCache = new Map();
function stripeColor(v, max) {   // diverging blue - white - red
  const t = Math.max(-1, Math.min(1, v / max));
  const lerp = (a, b, k) => Math.round(a + (b - a) * k);
  const [c0, c1] = t < 0 ? [[247, 247, 247], [33, 102, 172]] : [[247, 247, 247], [178, 24, 43]];
  const k = Math.abs(t);
  return `rgb(${lerp(c0[0], c1[0], k)},${lerp(c0[1], c1[1], k)},${lerp(c0[2], c1[2], k)})`;
}
async function stripesFor(region) {
  if (stripeCache.has(region)) return stripeCache.get(region);
  const res = await fetch(`${API}/analyze/detail`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ region_id: region, variable: "air_temperature", season: "all" }) });
  const json = await res.json();
  if (!json.result) throw new Error(json.error ? json.error.message : "No data");
  const byYear = {};
  for (const f of json.result.analysis.fit) {
    if (f.analysed === null || f.analysed === undefined) continue;
    const y = f.date.slice(0, 4); (byYear[y] ||= []).push(f.analysed);
  }
  const years = Object.keys(byYear).sort().filter((y) => byYear[y].length >= 9)
    .map((y) => ({ year: y, v: byYear[y].reduce((a, b) => a + b, 0) / byYear[y].length }));
  const out = { years, trend: json.result.trend };
  stripeCache.set(region, out);
  return out;
}
async function showStripes(region) {
  $$(".stripe-tabs .chip").forEach((c) => c.classList.toggle("active", c.dataset.region === region));
  const box = $("#stripes"), axis = $("#stripes-axis"), verdict = $("#stripes-verdict");
  box.classList.add("loading");
  try {
    const { years, trend } = await stripesFor(region);
    const max = Math.max(0.2, ...years.map((y) => Math.abs(y.v)));
    box.replaceChildren(...years.map((y, i) => {
      const s = document.createElement("span");
      s.style.background = stripeColor(y.v, max); s.style.setProperty("--i", i);
      s.title = `${y.year}: ${y.v >= 0 ? "+" : "−"}${Math.abs(y.v).toFixed(2)} °C vs this place's average`;
      return s;
    }));
    axis.innerHTML = `<span>${years[0].year}</span><span>${years[years.length - 1].year}</span>`;
    const slope = trend.sen_slope, sig = trend.significant;
    verdict.innerHTML = `<b class="${sig ? (slope > 0 ? "warm" : "cool") : "flat"}">${slope >= 0 ? "+" : "−"}${Math.abs(slope).toFixed(2)} °C per decade</b>
      <span>${sig ? "statistically significant" : "not statistically significant: could be noise"} · p ${trend.p_value < 0.001 ? "< 0.001" : "= " + trend.p_value.toFixed(3)}</span>`;
  } catch (e) {
    box.replaceChildren(Object.assign(document.createElement("p"), { className: "muted", textContent: `Could not load: ${e.message}` }));
  } finally { box.classList.remove("loading"); }
}
$$(".stripe-tabs .chip").forEach((c) => c.addEventListener("click", () => showStripes(c.dataset.region)));
new IntersectionObserver(([e], obs) => { if (e.isIntersecting) { showStripes("AMAZON_ARC"); obs.disconnect(); } }, { rootMargin: "300px" }).observe($("#climate"));

// ---------- vital signs from the variable catalogue ----------
async function loadVitals() {
  const grid = $("#vitals-grid");
  try {
    const { result } = await (await fetch(`${API}/catalog`)).json();
    grid.replaceChildren(...Object.entries(result.themes).map(([key, label], i) => {
      const vars = result.variables.filter((v) => v.themes.includes(key));
      const card = document.createElement("article");
      card.className = `vital tilt reveal in theme-${key}`; card.style.setProperty("--d", `${i * 80}ms`);
      card.innerHTML = `<div class="vital-head"><svg viewBox="0 0 40 40" aria-hidden="true">${THEME_ICON[key] || ""}</svg>
        <div><h3>${key[0].toUpperCase() + key.slice(1)}</h3><p>${label}</p></div></div>
        <ul>${vars.map((v) => `<li class="${v.available_now ? "live" : ""}"><span>${v.name}</span><small>${v.mission}${v.available_now ? " · <b>live</b>" : ""}</small></li>`).join("")}</ul>`;
      return card;
    }));
  } catch { grid.textContent = "The variable catalogue could not be loaded."; }
}
new IntersectionObserver(([e], obs) => { if (e.isIntersecting) { loadVitals(); obs.disconnect(); } }, { rootMargin: "400px" }).observe($("#vitals"));

// ---------- finale parallax (separate layers, composited transforms only) ----------
const finale = $("#finale"), layers = $$("#finale .landscape-layer"), sunEl = $("#finale .sun");
let finaleTick = false;
addEventListener("scroll", () => {
  if (REDUCED || finaleTick) return;
  finaleTick = true;
  requestAnimationFrame(() => {
    finaleTick = false;
    const r = finale.getBoundingClientRect();
    if (r.top > innerHeight || r.bottom < 0) return;
    const k = 1 - (r.top + r.height) / (innerHeight + r.height);
    layers.forEach((l, i) => { l.style.transform = `translate3d(0, ${((1 - k) * (i + 1) * 22).toFixed(1)}px, 0)`; });
    sunEl.style.transform = `translate3d(-50%, ${((1 - k) * 110).toFixed(1)}px, 0)`;
  });
}, { passive: true });

// ---------- "back to top" links: #top is the fixed bar, so scroll the window itself ----------
let pendingFocus = null;
function toTop() {
  window.scrollTo({ top: 0, behavior: REDUCED ? "auto" : "smooth" });
  // A smooth scroll can be cut short when lazy sections grow on the way up: finish the trip if it stalls.
  let last = scrollY, stalls = 0;
  const check = () => {
    if (scrollY <= 2) return;
    stalls = Math.abs(scrollY - last) < 1 ? stalls + 1 : 0; last = scrollY;
    if (stalls >= 6) { window.scrollTo({ top: 0, behavior: "auto" }); return; }
    requestAnimationFrame(check);
  };
  setTimeout(() => requestAnimationFrame(check), 250);
}
document.addEventListener("click", (e) => {
  const a = e.target.closest('a[href="#top"]');
  if (!a) return;
  e.preventDefault(); history.replaceState(null, "", location.pathname + location.search); toTop();
});

// ---------- start the light modules ----------
startRocket();
startMascot();
initGuide({ openInLab, flyTo: (id) => {
  pendingFocus = id;                 // applied when the hero is back in view (or now, if it already is)
  if (scrollY < innerHeight * 0.3 && globe) { globe.setSpin(false); globe.focusRegion(id, 2.8); pendingFocus = null; }
  toTop();
} });
