// "Trace", TrendTrace's own astronaut guide (original character). Waves hello on arrival,
// then docks in the corner and offers a short tip for each part of the page.
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

const ASTRONAUT = `
<svg class="astro" viewBox="0 0 200 250" aria-hidden="true">
  <defs>
    <linearGradient id="suit" x1="0" x2="1"><stop offset="0" stop-color="#c9d2de"/><stop offset=".35" stop-color="#ffffff"/><stop offset=".75" stop-color="#e8edf4"/><stop offset="1" stop-color="#aeb9c9"/></linearGradient>
    <radialGradient id="visor" cx=".38" cy=".32" r=".8"><stop offset="0" stop-color="#3ea0ff"/><stop offset=".45" stop-color="#123a78"/><stop offset="1" stop-color="#050d22"/></radialGradient>
    <radialGradient id="planet" cx=".35" cy=".35"><stop offset="0" stop-color="#7cc4ff"/><stop offset=".6" stop-color="#2c6fbb"/><stop offset="1" stop-color="#0b2a5a"/></radialGradient>
  </defs>
  <g class="astro-body">
    <!-- jet pack -->
    <rect x="58" y="98" width="84" height="74" rx="16" fill="#8592a6"/>
    <rect x="62" y="166" width="16" height="12" rx="3" fill="#5b667a"/><rect x="122" y="166" width="16" height="12" rx="3" fill="#5b667a"/>
    <g class="jet"><ellipse cx="70" cy="186" rx="6" ry="10" fill="#ffb36b"/><ellipse cx="130" cy="186" rx="6" ry="10" fill="#ffb36b"/>
      <ellipse cx="70" cy="184" rx="3" ry="6" fill="#fff6e0"/><ellipse cx="130" cy="184" rx="3" ry="6" fill="#fff6e0"/></g>
    <!-- legs -->
    <rect x="72" y="168" width="24" height="46" rx="11" fill="url(#suit)"/><rect x="104" y="168" width="24" height="46" rx="11" fill="url(#suit)"/>
    <rect x="70" y="204" width="28" height="16" rx="7" fill="#3b4558"/><rect x="102" y="204" width="28" height="16" rx="7" fill="#3b4558"/>
    <rect x="72" y="186" width="24" height="5" fill="#ff7a45"/><rect x="104" y="186" width="24" height="5" fill="#ff7a45"/>
    <!-- torso -->
    <rect x="62" y="108" width="76" height="72" rx="28" fill="url(#suit)"/>
    <rect x="82" y="128" width="36" height="24" rx="5" fill="#dfe6ef" stroke="#a9b5c6"/>
    <circle class="led l1" cx="91" cy="136" r="3" fill="#4ade80"/><circle class="led l2" cx="100" cy="136" r="3" fill="#ffc86b"/><circle class="led l3" cx="109" cy="136" r="3" fill="#ff7a45"/>
    <rect x="88" y="143" width="24" height="4" rx="2" fill="#7c8aa0"/>
    <svg x="66" y="114" width="16" height="16" viewBox="0 0 64 64"><use href="#tt-mark"/></svg>
    <!-- left arm (resting) -->
    <path d="M66 120 C52 132 48 150 52 168" stroke="url(#suit)" stroke-width="20" stroke-linecap="round" fill="none"/>
    <circle cx="52" cy="170" r="10" fill="#e9eef5" stroke="#b5c0cf"/>
    <!-- right arm (waving) -->
    <g class="wave-arm">
      <path d="M134 122 C150 112 158 96 160 78" stroke="url(#suit)" stroke-width="20" stroke-linecap="round" fill="none"/>
      <circle cx="160" cy="72" r="11" fill="#e9eef5" stroke="#b5c0cf"/>
      <rect x="148" y="94" width="18" height="5" rx="2" transform="rotate(-62 157 96)" fill="#2c6fbb"/>
    </g>
    <!-- helmet -->
    <circle cx="100" cy="70" r="48" fill="url(#suit)" stroke="#b9c3d2" stroke-width="2"/>
    <ellipse cx="100" cy="74" rx="36" ry="30" fill="url(#visor)" stroke="#d7dee8" stroke-width="3"/>
    <path d="M76 62 Q86 48 104 48" stroke="#ffffff" stroke-opacity=".7" stroke-width="4" stroke-linecap="round" fill="none"/>
    <circle cx="118" cy="88" r="7" fill="url(#planet)" opacity=".85"/>
    <!-- friendly eyes on the visor display -->
    <g class="eyes" stroke="#7df0ff" stroke-width="4" stroke-linecap="round" fill="none">
      <path d="M86 76 Q91 70 96 76"/><path d="M104 76 Q109 70 114 76"/>
    </g>
    <path d="M94 88 Q100 93 106 88" stroke="#7df0ff" stroke-width="3" stroke-linecap="round" fill="none" opacity=".9"/>
    <line x1="132" y1="34" x2="140" y2="18" stroke="#b9c3d2" stroke-width="3"/><circle class="antenna" cx="141" cy="16" r="4.5" fill="#ff7a45"/>
  </g>
</svg>`;

const TIPS = {
  hero: "Drag the globe and hover any country. The glowing markers are real NASA trends, coloured live.",
  missions: "These are the spacecraft behind our data. Aqua and Aura fly in the same orbit, minutes apart.",
  cases: "Watch for “not significant”. Delhi's NO₂ dips, but it could be noise, and saying so is honest science.",
  climate: "Each stripe is one year. Redder means warmer than that place's 2003–2024 average.",
  vitals: "Four variables are live now. Any other one can be tested by uploading a NASA Giovanni export.",
  how: "We remove the seasons first, so a monsoon can't pretend to be a trend.",
  impact: "Try it on your own city: draw a box in Giovanni, download the CSV, upload it in the lab.",
  trust: "The AI only rewords our numbers. If it changes a single one, code rejects it.",
  lab: "Start with “What's changing?”. It scans every region at once with a many-test check.",
};

export function startMascot() {
  const dock = document.createElement("div");
  dock.className = "mascot-dock";
  dock.innerHTML = `<button class="mascot-btn" type="button" aria-label="Trace, your guide: show a tip">${ASTRONAUT}</button>
    <div class="mascot-bubble" role="status" hidden><button class="bubble-x" type="button" aria-label="Close tip">×</button><b>Trace</b><p></p></div>`;
  document.body.append(dock);
  const bubble = dock.querySelector(".mascot-bubble"), text = bubble.querySelector("p");
  let current = "hero", hideTimer = null;
  function say(msg, ms = 6000) {
    text.textContent = msg; bubble.hidden = false; dock.classList.add("talking");
    clearTimeout(hideTimer); if (ms) hideTimer = setTimeout(() => { bubble.hidden = true; dock.classList.remove("talking"); }, ms);
  }
  dock.querySelector(".mascot-btn").addEventListener("click", () => {
    if (!bubble.hidden) { bubble.hidden = true; dock.classList.remove("talking"); } else say(TIPS[current] || TIPS.hero, 9000);
    dock.classList.add("wave"); setTimeout(() => dock.classList.remove("wave"), 1600);
  });
  bubble.querySelector(".bubble-x").addEventListener("click", () => { bubble.hidden = true; dock.classList.remove("talking"); });

  const seen = new Set();
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      current = e.target.id;
      if (!seen.has(current) && current !== "hero" && document.body.classList.contains("intro-done")) {
        seen.add(current); say(TIPS[current], 5500);
        dock.classList.add("wave"); setTimeout(() => dock.classList.remove("wave"), 1600);
      }
    }
  }, { rootMargin: "-40% 0px -40% 0px" });
  Object.keys(TIPS).forEach((id) => { const n = document.getElementById(id); if (n) io.observe(n); });

  // ---------- arrival: float in, wave, say hello ----------
  let skip = false;
  try { skip = sessionStorage.getItem("tt-intro") === "1"; } catch { /* storage blocked: show it */ }
  if (skip) { document.body.classList.add("intro-done"); return; }
  const intro = document.createElement("div");
  intro.className = "intro";
  intro.innerHTML = `<div class="intro-stage">${ASTRONAUT}
      <div class="intro-bubble"><span class="mono">Incoming transmission</span><p class="typed"></p>
        <div class="intro-actions"><button class="btn btn-primary" type="button" data-go><span>Let's investigate</span></button>
        <button class="btn btn-ghost" type="button" data-skip><span>Skip</span></button></div></div></div>`;
  document.body.append(intro);
  const msg = "Hi, I'm Trace! I fly with NASA satellite data. Let's find out what's really changing on Earth, and what's just noise.";
  const typed = intro.querySelector(".typed");
  function begin() {
    intro.classList.add("show");
    if (REDUCED) { typed.textContent = msg; return; }
    let i = 0; const t = setInterval(() => { typed.textContent = msg.slice(0, ++i); if (i >= msg.length) clearInterval(t); }, 22);
    setTimeout(finish, 11000);  // never hold the page hostage
  }
  let done = false;
  function finish() {
    if (done) return; done = true;
    try { sessionStorage.setItem("tt-intro", "1"); } catch { /* ignore */ }
    const from = intro.querySelector(".astro").getBoundingClientRect(), to = dock.querySelector(".astro").getBoundingClientRect();
    const fly = intro.querySelector(".astro");
    fly.style.transition = REDUCED ? "none" : "transform .9s cubic-bezier(.6,-0.2,.3,1.2)";
    fly.style.transformOrigin = "top left";
    fly.style.transform = `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${to.width / from.width})`;
    intro.classList.add("leaving");
    setTimeout(() => { intro.remove(); document.body.classList.add("intro-done"); }, REDUCED ? 0 : 950);
  }
  intro.querySelector("[data-go]").addEventListener("click", finish);
  intro.querySelector("[data-skip]").addEventListener("click", finish);
  addEventListener("keydown", (e) => { if (e.key === "Escape" && intro.isConnected) finish(); });
  const whenReady = () => (document.body.classList.contains("ready") ? begin() : setTimeout(whenReady, 120));
  whenReady();
}
