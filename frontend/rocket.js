// Scroll-driven launch: the page is the flight. The rocket sits on its pad at the top of the page,
// ignites when you start scrolling, climbs with the scroll position, and reaches orbit at the footer.
// Canvas 2D particles: additive fire (white-hot core -> orange -> red), shock diamonds, glow, and smoke.
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const STAGES = [
  [0.0, "ON PAD · T−0"], [0.012, "LIFTOFF"], [0.16, "MAX-Q"], [0.4, "STAGE SEP"], [0.68, "COAST"], [0.95, "ORBIT ✓"],
];

export function startRocket() {
  const canvas = document.createElement("canvas");
  canvas.className = "rocket-canvas";
  canvas.setAttribute("aria-hidden", "true");
  document.body.append(canvas);
  const ctx = canvas.getContext("2d");
  // Only a narrow strip on the right is drawn (not the whole screen): far fewer pixels per frame.
  let W = 0, H = 0, VW = 0, dpr = 1, enabled = false, S = 0.8, compact = false;

  // Pre-rendered soft sprites (cheap to draw thousands of times).
  function sprite(r, g, b) {
    const c = document.createElement("canvas"); c.width = c.height = 64;
    const x = c.getContext("2d"), gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, `rgba(${r},${g},${b},1)`); gr.addColorStop(0.4, `rgba(${r},${g},${b},.55)`); gr.addColorStop(1, `rgba(${r},${g},${b},0)`);
    x.fillStyle = gr; x.fillRect(0, 0, 64, 64); return c;
  }
  const FIRE = [sprite(255, 232, 170), sprite(255, 178, 70), sprite(255, 120, 35), sprite(220, 60, 25), sprite(110, 35, 20)];
  const SMOKE = sprite(150, 158, 172);
  const GLOW = sprite(255, 140, 50);

  const fire = [], smoke = [];
  let p = 0, pShown = 0, lastY = scrollY, vel = 0, thrust = 0, tilt = 0, lastT = performance.now(), stage = "", stageFlash = 0;

  function resize() {
    VW = innerWidth; H = innerHeight;
    enabled = VW >= 600;
    // Scale with the screen so it is visible at any zoom level; the page reserves a matching rail (--rail).
    S = VW >= 1500 ? 0.8 : VW >= 1100 ? 0.66 : VW >= 800 ? 0.54 : 0.44;
    compact = VW < 1100;
    W = compact ? 120 : 210;
    dpr = Math.min(devicePixelRatio, 1.5);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
    canvas.hidden = !enabled;
    document.documentElement.style.setProperty("--rail", enabled ? `${Math.round(60 * S / 0.8)}px` : "0px");
    dirty = true;
  }
  let dirty = true;
  addEventListener("scroll", () => { dirty = true; }, { passive: true });
  addEventListener("resize", resize);

  const progress = () => { const max = document.documentElement.scrollHeight - innerHeight; return max > 0 ? Math.min(1, Math.max(0, scrollY / max)) : 0; };
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

  function drawRocket(x, y, a, s) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(a); ctx.scale(s, s);
    // fins
    const fin = ctx.createLinearGradient(-26, 0, 26, 0); fin.addColorStop(0, "#b8461d"); fin.addColorStop(0.5, "#ff7a45"); fin.addColorStop(1, "#a63d17");
    ctx.fillStyle = fin;
    ctx.beginPath(); ctx.moveTo(-12, -42); ctx.lineTo(-27, -8); ctx.lineTo(-27, 4); ctx.lineTo(-12, -12); ctx.closePath(); ctx.fill();
    ctx.beginPath(); ctx.moveTo(12, -42); ctx.lineTo(27, -8); ctx.lineTo(27, 4); ctx.lineTo(12, -12); ctx.closePath(); ctx.fill();
    // nozzle bell
    const bell = ctx.createLinearGradient(-9, 0, 9, 0); bell.addColorStop(0, "#2a3140"); bell.addColorStop(0.5, "#8a95a8"); bell.addColorStop(1, "#262c39");
    ctx.fillStyle = bell; ctx.beginPath(); ctx.moveTo(-6, -4); ctx.lineTo(6, -4); ctx.lineTo(9.5, 6); ctx.lineTo(-9.5, 6); ctx.closePath(); ctx.fill();
    // body + nose
    const body = ctx.createLinearGradient(-13, 0, 13, 0);
    body.addColorStop(0, "#7b8698"); body.addColorStop(0.3, "#ffffff"); body.addColorStop(0.65, "#dfe5ee"); body.addColorStop(1, "#6f7a8d");
    ctx.fillStyle = body; ctx.beginPath();
    ctx.moveTo(-12, -4); ctx.lineTo(-12, -86); ctx.bezierCurveTo(-12, -104, -5, -118, 0, -126); ctx.bezierCurveTo(5, -118, 12, -104, 12, -86); ctx.lineTo(12, -4); ctx.closePath(); ctx.fill();
    // stripes
    ctx.save(); ctx.clip();
    ctx.fillStyle = "#ff7a45"; ctx.fillRect(-13, -92, 26, 5);
    ctx.fillStyle = "#2c6fbb"; ctx.fillRect(-13, -36, 26, 7);
    ctx.fillStyle = "rgba(0,0,0,.18)"; ctx.fillRect(-13, -12, 26, 2);
    ctx.restore();
    // window
    const glass = ctx.createRadialGradient(-1.5, -68, 0.5, 0, -66, 6); glass.addColorStop(0, "#c9ecff"); glass.addColorStop(0.5, "#3d8fe0"); glass.addColorStop(1, "#0b2a5a");
    ctx.fillStyle = "#c4ccd8"; ctx.beginPath(); ctx.arc(0, -66, 7, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = glass; ctx.beginPath(); ctx.arc(0, -66, 5, 0, Math.PI * 2); ctx.fill();
    // centre fin
    ctx.fillStyle = "#d0592a"; ctx.fillRect(-1.6, -30, 3.2, 32);
    ctx.restore();
  }

  function flame(x, y, a, k, t) {
    // big ambient glow
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    const gR = (90 * k + 20) * S / 0.8;
    ctx.globalAlpha = 0.45 * k; ctx.drawImage(GLOW, x - gR, y + 18 - gR, gR * 2, gR * 2); ctx.globalAlpha = 1;
    // plume core: outer orange, inner white-blue (teardrop), length flickers
    ctx.translate(x, y); ctx.rotate(a);
    ctx.scale(S / 0.8, S / 0.8);
    const L = (40 + 85 * k) * (0.9 + Math.random() * 0.18), wid = 8 + 4 * k;
    for (const [w, len, c0, c1] of [[wid * 1.5, L, "rgba(255,100,30,.6)", "rgba(255,50,15,0)"], [wid, L * 0.72, "rgba(255,190,90,.85)", "rgba(255,120,40,0)"], [wid * 0.45, L * 0.4, "rgba(255,250,235,.95)", "rgba(170,210,255,0)"]]) {
      const g2 = ctx.createLinearGradient(0, 6, 0, 6 + len); g2.addColorStop(0, c0); g2.addColorStop(1, c1);
      ctx.fillStyle = g2; ctx.beginPath(); ctx.moveTo(-w * 0.55, 6);
      ctx.bezierCurveTo(-w, 6 + len * 0.3, -w * 0.3, 6 + len * 0.8, 0, 6 + len);
      ctx.bezierCurveTo(w * 0.3, 6 + len * 0.8, w, 6 + len * 0.3, w * 0.55, 6); ctx.closePath(); ctx.fill();
    }
    // shock diamonds at high thrust
    if (k > 0.55) {
      for (let i = 1; i <= 3; i++) {
        const yy = 6 + i * L * 0.17, r = (wid * 0.45) * (1 - i * 0.18);
        ctx.fillStyle = `rgba(255,255,240,${(k - 0.5) * 0.9 / i})`;
        ctx.beginPath(); ctx.ellipse(0, yy, r, r * 1.6, 0, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.restore();
  }

  function emit(x, y, a, k, dt) {
    const nx = x - Math.sin(a) * 8, ny = y + Math.cos(a) * 8;
    const nFire = Math.round((24 + 80 * k) * dt * 6);
    const z = S / 0.8;
    for (let i = 0; i < nFire; i++) {
      const sp = 260 + 420 * k * Math.random();
      fire.push({ x: nx + (Math.random() - 0.5) * 8 * z, y: ny, vx: ((Math.random() - 0.5) * 70 - Math.sin(a) * sp * 0.3) * z, vy: sp * z, life: 0, max: 0.18 + Math.random() * 0.32, size: (10 + 18 * k * Math.random()) * z });
    }
    const nSmoke = Math.round((4 + 16 * k) * dt * 6);
    for (let i = 0; i < nSmoke; i++) {
      smoke.push({ x: nx + (Math.random() - 0.5) * 16 * z, y: ny + (40 + Math.random() * 40 * k) * z, vx: (Math.random() - 0.5) * 40 * z, vy: (40 + 90 * Math.random() * k) * z, life: 0, max: 1.2 + Math.random() * 1.2, size: (18 + Math.random() * 14) * z, a: 0.1 + Math.random() * 0.1 });
    }
  }
  function steam(x, y, dt) {   // idle venting on the pad
    if (Math.random() < dt * 5) smoke.push({ x: x + (Math.random() - 0.5) * 30, y: y + 4, vx: (Math.random() - 0.5) * 40, vy: -10 - Math.random() * 20, life: 0, max: 1.6, size: 10, a: 0.08 });
  }

  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - lastT) / 1000); lastT = now;
    if (!enabled || document.hidden) return;
    // Nothing moving (in orbit, or parked with no particles): skip the frame entirely.
    if (!dirty && thrust < 0.01 && fire.length === 0 && smoke.length === 0 && Math.abs(p - pShown) < 0.0005 && pShown > 0.006) return;
    dirty = false;
    p = progress();
    const dy = scrollY - lastY; lastY = scrollY;
    vel += ((dy / Math.max(dt, 0.001)) - vel) * Math.min(1, dt * 5);
    pShown += (p - pShown) * Math.min(1, dt * (REDUCED ? 60 : 7));

    const onPad = pShown < 0.006, inOrbit = pShown > 0.95;
    const target = onPad || inOrbit ? 0 : Math.min(1, 0.32 + Math.abs(vel) / 1800);
    thrust += (target - thrust) * Math.min(1, dt * 5);
    tilt += ((Math.max(-0.14, Math.min(0.14, vel * 0.00012)) + (thrust > 0.1 ? Math.sin(now / 90) * 0.01 * thrust : 0)) - tilt) * Math.min(1, dt * 4);

    const tx = W - Math.round(46 * S / 0.8), x = tx + Math.sin(now / 1400) * (onPad ? 0 : 3), top = 200, bottom = H - 40;
    const y = bottom - (bottom - top) * ease(pShown);
    const s = S;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);

    // flight track and stage marks
    ctx.strokeStyle = "rgba(124,196,255,.16)"; ctx.setLineDash([3, 6]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(tx, top - 40); ctx.lineTo(tx, bottom + 10); ctx.stroke(); ctx.setLineDash([]);
    const prog = ctx.createLinearGradient(0, bottom, 0, top); prog.addColorStop(0, "rgba(255,122,69,.7)"); prog.addColorStop(1, "rgba(124,196,255,.7)");
    ctx.strokeStyle = prog; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(tx, bottom + 10); ctx.lineTo(tx, y + 10); ctx.stroke();
    ctx.font = "600 10px 'JetBrains Mono', monospace"; ctx.textAlign = "right";
    for (const [at, name] of STAGES.slice(1)) {
      const yy = bottom - (bottom - top) * ease(at), passed = pShown >= at;
      ctx.fillStyle = passed ? "rgba(255,200,107,.9)" : "rgba(143,163,191,.45)";
      ctx.beginPath(); ctx.arc(tx, yy, passed ? 3 : 2, 0, Math.PI * 2); ctx.fill();
      if (!compact && Math.abs(yy - y) > 140) ctx.fillText(name, tx - 12, yy + 3.5);
    }
    // launch pad
    if (pShown < 0.08) {
      ctx.globalAlpha = 1 - pShown / 0.08;
      const z = S / 0.8, tw = tx - 30 * z;
      ctx.fillStyle = "#1c2740"; ctx.fillRect(tx - 34 * z, bottom + 8, 68 * z, 5);
      ctx.strokeStyle = "#3b4c6e"; ctx.lineWidth = 2; ctx.beginPath();
      ctx.moveTo(tw, bottom + 8); ctx.lineTo(tw, bottom - 112 * z); ctx.moveTo(tw, bottom - 80 * z); ctx.lineTo(tw + 16 * z, bottom - 80 * z);
      for (let i = 0; i < 6; i++) { ctx.moveTo(tw - 4 * z, bottom + 8 - i * 20 * z); ctx.lineTo(tw + 4 * z, bottom - 12 * z - i * 20 * z); }
      ctx.stroke(); ctx.globalAlpha = 1;
    }

    // particles: smoke first (normal blend), then fire (additive)
    if (!REDUCED) {
      if (thrust > 0.02) emit(x, y, tilt, thrust, dt); else if (onPad) steam(x, y, dt);
      for (let i = smoke.length - 1; i >= 0; i--) {
        const q = smoke[i]; q.life += dt; if (q.life > q.max) { smoke.splice(i, 1); continue; }
        q.x += q.vx * dt; q.y += q.vy * dt; q.vx *= 0.98; q.vy *= 0.97;
        const t = q.life / q.max, r = q.size * (1 + t * 3.2);
        ctx.globalAlpha = q.a * (1 - t); ctx.drawImage(SMOKE, q.x - r, q.y - r, r * 2, r * 2);
      }
      ctx.globalCompositeOperation = "lighter";
      for (let i = fire.length - 1; i >= 0; i--) {
        const q = fire[i]; q.life += dt; if (q.life > q.max) { fire.splice(i, 1); continue; }
        q.x += q.vx * dt; q.y += q.vy * dt;
        const t = q.life / q.max, r = q.size * (0.6 + t * 1.3), img = FIRE[Math.min(4, Math.floor(t * 5))];
        ctx.globalAlpha = (1 - t) * (t < 0.2 ? 0.45 : 0.6); ctx.drawImage(img, q.x - r, q.y - r, r * 2, r * 2);
      }
      ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
      if (fire.length > 420) fire.splice(0, fire.length - 420);
      if (smoke.length > 140) smoke.splice(0, smoke.length - 140);
    }
    if (thrust > 0.02) flame(x - Math.sin(tilt) * 6 * s, y + Math.cos(tilt) * 4 * s, tilt, REDUCED ? 0.4 : thrust, now);
    drawRocket(x, y, tilt, s);

    // telemetry readout + stage callouts
    const alt = Math.round(pShown * 408);
    let name = STAGES[0][1]; for (const [at, n] of STAGES) if (pShown >= at) name = n;
    if (name !== stage) { stage = name; stageFlash = 1.6; }
    stageFlash = Math.max(0, stageFlash - dt);
    if (compact) return;   // small screens: rocket and flame only, no text
    ctx.textAlign = "right"; ctx.font = "600 11px 'JetBrains Mono', monospace";
    ctx.fillStyle = "rgba(232,238,247,.85)"; ctx.fillText(`ALT ${alt} km`, x - 44, y - 70);
    ctx.fillStyle = "rgba(143,163,191,.8)"; ctx.fillText(`THR ${Math.round(thrust * 100)}%`, x - 44, y - 56);
    if (stageFlash > 0) {
      ctx.globalAlpha = Math.min(1, stageFlash);
      ctx.font = "700 13px 'Space Grotesk', sans-serif"; ctx.fillStyle = "#ffc86b"; ctx.fillText(stage, x - 44, y - 90);
      ctx.globalAlpha = 1;
    }
  }
  resize();
  requestAnimationFrame(frame);
}
