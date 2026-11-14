// TrendTrace motion layer: boot sequence, globe wiring, scroll story, counters, tilt, magnetic buttons.
// Plain ES module, no dependencies besides globe.js. Everything respects prefers-reduced-motion.
import { createGlobe } from "/static/globe.js";

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const FINE = matchMedia("(pointer: fine)").matches;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---------- boot ----------
const boot = $("#boot");
const bootStart = performance.now();
function endBoot() {
  if (!boot || boot.classList.contains("done")) return;
  const wait = REDUCED ? 0 : Math.max(0, 1300 - (performance.now() - bootStart));
  setTimeout(() => { boot.classList.add("done"); document.body.classList.add("ready"); }, wait);
}
setTimeout(endBoot, 2600); // never block the page

// ---------- open the lab on a region + variable ----------
function openInLab(region, variable) {
  $("#lab").scrollIntoView({ behavior: REDUCED ? "auto" : "smooth" });
  if (window.ttOpenAnalysis) window.ttOpenAnalysis(region, variable);
}

// ---------- globe ----------
const statusEl = $("#layer-status span");
const LABELS = { aod: "Aerosol haze (MODIS)", no2: "NO₂ (OMI)", air_temperature: "Air temperature (NASA POWER)", rainfall: "Rainfall (GPM IMERG / NASA POWER)" };
let globe = null;
createGlobe($("#globe-wrap"), {
  layer: "aod",
  onSelect: openInLab,
  onLayer(layer, data, source) {
    $$(".layer-bar .chip").forEach((c) => c.classList.toggle("active", c.dataset.layer === layer));
    if (!data) return;
    statusEl.textContent = `${source === "live" ? "Live" : "Last computed"} · ${LABELS[layer] || layer} · ${data.summary}`;
    $("#layer-status").classList.toggle("live", source === "live");
  },
}).then((g) => { globe = g; endBoot(); })
  .catch(() => { $("#globe-wrap").classList.add("no-webgl"); endBoot(); });

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
    if (!globe) continue;
    globe.setLayer(c.dataset.layer);
    globe.flyTo(Number(c.dataset.lat), Number(c.dataset.lon), Number(c.dataset.dist) || 2.8);
    runCounters(c);
  }
}, { rootMargin: "-45% 0px -45% 0px" });
cases.forEach((c) => {
  caseObserver.observe(c);
  $(".run", c).addEventListener("click", () => openInLab(c.dataset.region, c.dataset.variable));
});
// Back in the hero: spin again. Below the stage: nothing to do (render loop pauses itself).
new IntersectionObserver(([e]) => {
  if (!globe) return;
  if (e.isIntersecting) { activeCase = null; cases.forEach((x) => x.classList.remove("active")); globe.setSpin(true); globe.flyTo(22, 40, 3.4, 1400); }
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
addEventListener("scroll", () => bar.classList.toggle("scrolled", scrollY > 30), { passive: true });

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
