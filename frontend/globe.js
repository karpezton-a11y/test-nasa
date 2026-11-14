// TrendTrace 3D globe: three.js, no build step.
// Dotted land, country hover names, atmosphere glow, live trend markers from /api/v1/scan,
// an animated LA–Delhi arc, and a fly-to camera used by the "Case files" scroll story.
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";

const API = "/api/v1";
const DEG = Math.PI / 180;
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const COLORS = { up: 0xff7a45, down: 0x4aa3ff, none: 0x8191a8, fdr: 0xffc86b };
const CSS = { up: "#ff7a45", down: "#4aa3ff", none: "#8191a8", fdr: "#ffc86b" };
const SHORT = { IGP: "Indo-Gangetic Plain", TN: "Tamil Nadu", DELHI: "Delhi", LA_BASIN: "Los Angeles",
                AMAZON_ARC: "Southern Amazon", SAHEL: "Central Sahel" };

// Matches three.js SphereGeometry UVs, so an equirectangular canvas lines up with these points.
export function latLonToVec3(lat, lon, r = 1) {
  const phi = (90 - lat) * DEG, theta = (lon + 180) * DEG;
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}
function vec3ToLatLon(v) {
  const n = v.clone().normalize();
  let lon = Math.atan2(n.z, -n.x) / DEG - 180;
  if (lon < -180) lon += 360;
  return { lat: 90 - Math.acos(THREE.MathUtils.clamp(n.y, -1, 1)) / DEG, lon };
}

// ---------- country geometry (Natural Earth 1:110m via world-atlas, public domain) ----------
function inRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 2; i < ring.length; j = i, i += 2) {
    const xi = ring[i], yi = ring[i + 1], xj = ring[j], yj = ring[j + 1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function countryAt(countries, lat, lon) {
  for (const c of countries) {
    const [x0, y0, x1, y1] = c.b;
    if (lon < x0 || lon > x1 || lat < y0 || lat > y1) continue;
    for (const poly of c.p) {
      let inside = false;
      for (const ring of poly) if (inRing(lon, lat, ring)) inside = !inside;
      if (inside) return c;
    }
  }
  return null;
}
function tracePolys(ctx, polys, W, H) {
  ctx.beginPath();
  for (const poly of polys) for (const ring of poly) {
    for (let i = 0; i < ring.length; i += 2) {
      const x = ((ring[i] + 180) / 360) * W, y = ((90 - ring[i + 1]) / 180) * H;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
  }
}

// ---------- shaders ----------
const baseShader = {
  vertexShader: `varying vec2 vUv; varying vec3 vN; varying vec3 vP;
    void main(){ vUv = uv; vN = normalize(normalMatrix * normal); vec4 mv = modelViewMatrix * vec4(position,1.0); vP = mv.xyz; gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `uniform sampler2D uMap; varying vec2 vUv; varying vec3 vN; varying vec3 vP;
    void main(){ vec3 col = texture2D(uMap, vUv).rgb;
      float f = pow(1.0 - max(dot(normalize(-vP), vN), 0.0), 2.6);
      col += vec3(0.18, 0.5, 1.0) * f * 0.85; gl_FragColor = vec4(col, 1.0); }`,
};
const atmoShader = {
  vertexShader: `varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `varying vec3 vN; void main(){ float i = pow(0.68 - dot(vN, vec3(0.0,0.0,1.0)), 3.4);
      gl_FragColor = vec4(0.25, 0.6, 1.0, 1.0) * i; }`,
};
const dotShader = {
  vertexShader: `attribute float aRand; uniform float uTime; uniform float uSize; varying float vA; varying float vR;
    void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vec3 n = normalize(normalMatrix * position);
      vA = clamp(-dot(normalize(mv.xyz), n) * 1.6, 0.0, 1.0); vR = aRand;
      gl_PointSize = uSize * (1.0 / -mv.z) * (0.75 + 0.5 * aRand); gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `uniform float uTime; varying float vA; varying float vR;
    void main(){ float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard;
      float tw = 0.6 + 0.4 * sin(uTime * 1.3 + vR * 40.0);
      vec3 c = mix(vec3(0.33,0.78,1.0), vec3(1.0), step(0.965, vR) * 0.8);
      gl_FragColor = vec4(c, smoothstep(0.5, 0.1, d) * vA * tw); }`,
};
const starShader = {
  vertexShader: `attribute float aRand; uniform float uTime; varying float vT;
    void main(){ vT = 0.55 + 0.45 * sin(uTime * (0.6 + aRand) + aRand * 50.0);
      vec4 mv = modelViewMatrix * vec4(position,1.0); gl_PointSize = 1.0 + aRand * 2.2; gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `varying float vT; void main(){ float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard;
      gl_FragColor = vec4(vec3(0.85,0.9,1.0), smoothstep(0.5,0.0,d) * vT); }`,
};
const beamShader = {
  vertexShader: `uniform float uH; varying float vH; void main(){ vH = position.y / uH; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `uniform vec3 uColor; uniform float uTime; varying float vH;
    void main(){ float pulse = 0.65 + 0.35 * sin(uTime * 3.0 - vH * 8.0); gl_FragColor = vec4(uColor, (1.0 - vH) * 0.9 * pulse); }`,
};
const arcShader = {
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `uniform float uTime; uniform float uShow; varying vec2 vUv;
    void main(){ float head = fract(uTime * 0.18); float d = vUv.x - head; if (d > 0.0) d -= 1.0;
      float glow = exp(d * 9.0); float base = 0.18;
      vec3 c = mix(vec3(1.0,0.48,0.27), vec3(0.29,0.64,1.0), vUv.x);
      gl_FragColor = vec4(c, (base + glow) * uShow); }`,
};

// ---------- the globe ----------
export async function createGlobe(wrap, opts = {}) {
  const canvas = wrap.querySelector("canvas");
  const tip = wrap.querySelector(".globe-tip");
  const labelLayer = wrap.querySelector(".globe-labels");
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  } catch (e) { wrap.classList.add("no-webgl"); throw e; }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 200);
  camera.position.copy(latLonToVec3(22, 40, 3.4));
  const controls = new OrbitControls(camera, canvas);
  Object.assign(controls, { enableDamping: true, dampingFactor: 0.06, enablePan: false, enableZoom: false,
                            rotateSpeed: 0.5, autoRotate: !REDUCED, autoRotateSpeed: 0.45, minDistance: 1.6, maxDistance: 7 });

  const countries = await fetch("/static/data/countries.json").then((r) => r.json());

  // Surface texture: deep ocean, faint graticule, land fill and glowing borders.
  const W = 4096, H = 2048, tex = document.createElement("canvas");
  tex.width = W; tex.height = H;
  const g = tex.getContext("2d");
  const ocean = g.createLinearGradient(0, 0, 0, H);
  ocean.addColorStop(0, "#04101f"); ocean.addColorStop(0.5, "#061a33"); ocean.addColorStop(1, "#04101f");
  g.fillStyle = ocean; g.fillRect(0, 0, W, H);
  g.strokeStyle = "rgba(90,150,220,0.10)"; g.lineWidth = 2;
  for (let lon = -180; lon <= 180; lon += 15) { const x = ((lon + 180) / 360) * W; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
  for (let lat = -75; lat <= 75; lat += 15) { const y = ((90 - lat) / 180) * H; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  g.fillStyle = "#0c2747"; g.strokeStyle = "rgba(110,190,255,0.55)"; g.lineWidth = 2.2;
  for (const c of countries) { tracePolys(g, c.p, W, H); g.fill("evenodd"); g.stroke(); }
  const surface = new THREE.CanvasTexture(tex);
  surface.colorSpace = THREE.SRGBColorSpace;
  surface.anisotropy = renderer.capabilities.getMaxAnisotropy();

  const globe = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96),
    new THREE.ShaderMaterial({ uniforms: { uMap: { value: surface } }, ...baseShader }));
  scene.add(globe);

  // Hover highlight lives on its own transparent layer, redrawn only when the country changes.
  const hl = document.createElement("canvas"); hl.width = 2048; hl.height = 1024;
  const hg = hl.getContext("2d"), hlTex = new THREE.CanvasTexture(hl);
  hlTex.colorSpace = THREE.SRGBColorSpace;
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.0015, 96, 72),
    new THREE.MeshBasicMaterial({ map: hlTex, transparent: true, depthWrite: false })));

  // Land dots: an even Fibonacci lattice, kept where the land mask is filled.
  const mask = document.createElement("canvas"); mask.width = 1024; mask.height = 512;
  const mg = mask.getContext("2d", { willReadFrequently: true });
  mg.fillStyle = "#fff"; for (const c of countries) { tracePolys(mg, c.p, 1024, 512); mg.fill("evenodd"); }
  const md = mg.getImageData(0, 0, 1024, 512).data;
  const N = 70000, pos = [], rnd = [], golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2, rad = Math.sqrt(1 - y * y), th = golden * i;
    const v = new THREE.Vector3(Math.cos(th) * rad, y, Math.sin(th) * rad);
    const { lat, lon } = vec3ToLatLon(v);
    const px = Math.min(1023, Math.floor(((lon + 180) / 360) * 1024)), py = Math.min(511, Math.floor(((90 - lat) / 180) * 512));
    if (md[(py * 1024 + px) * 4] > 128) { v.multiplyScalar(1.004); pos.push(v.x, v.y, v.z); rnd.push(Math.random()); }
  }
  const dotGeo = new THREE.BufferGeometry();
  dotGeo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  dotGeo.setAttribute("aRand", new THREE.Float32BufferAttribute(rnd, 1));
  const dotMat = new THREE.ShaderMaterial({ uniforms: { uTime: { value: 0 }, uSize: { value: 9 * renderer.getPixelRatio() } },
    transparent: true, depthWrite: false, ...dotShader });
  scene.add(new THREE.Points(dotGeo, dotMat));

  // Atmosphere halo.
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.16, 64, 48),
    new THREE.ShaderMaterial({ side: THREE.BackSide, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, ...atmoShader })));

  // Starfield.
  const sp = [], sr = [];
  for (let i = 0; i < 5000; i++) {
    const v = new THREE.Vector3().randomDirection().multiplyScalar(40 + Math.random() * 40);
    sp.push(v.x, v.y, v.z); sr.push(Math.random());
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.Float32BufferAttribute(sp, 3));
  starGeo.setAttribute("aRand", new THREE.Float32BufferAttribute(sr, 1));
  const starMat = new THREE.ShaderMaterial({ uniforms: { uTime: { value: 0 } }, transparent: true, depthWrite: false, ...starShader });
  const stars = new THREE.Points(starGeo, starMat);
  scene.add(stars);

  // ---------- region markers ----------
  const markerGroup = new THREE.Group(); scene.add(markerGroup);
  const markers = new Map();          // region_id -> {group, rings, beam, core, outline, hit, label, row, center}
  const hitTargets = [];
  function outlineFor(bbox) {
    const [w, s, e, n] = bbox, pts = [], step = 0.5;
    const edge = (a0, b0, a1, b1) => { const k = Math.max(2, Math.ceil(Math.max(Math.abs(a1 - a0), Math.abs(b1 - b0)) / step));
      for (let i = 0; i < k; i++) pts.push(latLonToVec3(b0 + ((b1 - b0) * i) / k, a0 + ((a1 - a0) * i) / k, 1.004)); };
    edge(w, n, e, n); edge(e, n, e, s); edge(e, s, w, s); edge(w, s, w, n);
    return new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ transparent: true, opacity: 0.95 }));
  }
  function buildMarker(region) {
    const [w, s, e, n] = region.bbox, lat = (s + n) / 2, lon = (w + e) / 2;
    const normal = latLonToVec3(lat, lon, 1).normalize();
    const group = new THREE.Group();
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), normal);
    const rings = [0, 0.8].map((phase) => {
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.018, 0.024, 48),
        new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide }));
      ring.position.copy(normal).multiplyScalar(1.006); ring.lookAt(normal.clone().multiplyScalar(2));
      ring.userData.phase = phase; group.add(ring); return ring;
    });
    const beamH = 0.22;
    const beamGeo = new THREE.CylinderGeometry(0.0035, 0.0035, beamH, 8, 1, true); beamGeo.translate(0, beamH / 2, 0);
    const beam = new THREE.Mesh(beamGeo, new THREE.ShaderMaterial({ uniforms: { uColor: { value: new THREE.Color() }, uH: { value: beamH }, uTime: { value: 0 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, ...beamShader }));
    beam.quaternion.copy(q); beam.position.copy(normal).multiplyScalar(1.0);
    group.add(beam);
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.011, 16, 12), new THREE.MeshBasicMaterial());
    core.position.copy(normal).multiplyScalar(1.006); group.add(core);
    const outline = outlineFor(region.bbox); group.add(outline);
    const hit = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 6), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }));
    hit.position.copy(normal).multiplyScalar(1.02); hit.userData.regionId = region.region_id; group.add(hit); hitTargets.push(hit);
    const label = document.createElement("button");
    label.className = "globe-label"; label.type = "button";
    label.innerHTML = `<i></i><span>${SHORT[region.region_id] || region.name}</span>`;
    label.addEventListener("click", () => opts.onSelect && opts.onSelect(region.region_id, state.layer));
    labelLayer.append(label);
    markerGroup.add(group);
    markers.set(region.region_id, { region, group, rings, beam, core, outline, hit, label, row: null, normal, lat, lon });
  }

  // ---------- the LA–Delhi arc ----------
  const la = latLonToVec3(34.0, -118.15, 1).normalize(), dl = latLonToVec3(28.6, 77.2, 1).normalize();
  const arcPts = [];
  for (let i = 0; i <= 160; i++) {
    const t = i / 160, v = new THREE.Vector3().copy(la).lerp(dl, t);
    // slerp along the great circle, lifted off the surface
    const qa = new THREE.Quaternion().setFromUnitVectors(la, dl), qq = new THREE.Quaternion().slerp(qa, t);
    v.copy(la).applyQuaternion(qq).multiplyScalar(1.01 + 0.42 * Math.sin(Math.PI * t));
    arcPts.push(v);
  }
  const arcMat = new THREE.ShaderMaterial({ uniforms: { uTime: { value: 0 }, uShow: { value: 0 } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, ...arcShader });
  const arc = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(arcPts), 240, 0.004, 8, false), arcMat);
  scene.add(arc);

  // ---------- state, layers and live data ----------
  const state = { layer: opts.layer || "aod", snapshot: null, live: {}, hoverCountry: null, hoverRegion: null, flying: null, spin: !REDUCED };
  function kindOf(row) {
    if (!row) return "none";
    if (row.status === "significant") return row.sen_slope > 0 ? "up" : "down";
    if (row.status === "significant_before_fdr_only") return "fdr";
    return "none";
  }
  function paint() {
    const layer = state.live[state.layer] || state.snapshot?.layers[state.layer];
    const rows = Object.fromEntries((layer?.rows || []).map((r) => [r.region_id, r]));
    for (const m of markers.values()) {
      const has = m.region.variables.includes(state.layer);
      m.group.visible = has; m.label.hidden = !has;
      m.row = rows[m.region.region_id] || null;
      const kind = kindOf(m.row), col = new THREE.Color(COLORS[kind]);
      m.rings.forEach((r) => r.material.color.copy(col));
      m.core.material.color.copy(col); m.outline.material.color.copy(col);
      m.beam.material.uniforms.uColor.value.copy(col);
      const pct = m.row?.percent_change_per_decade;
      const h = kind === "none" ? 0.25 : Math.min(2.4, 0.6 + Math.abs(pct || 30) / 25);
      m.beam.scale.set(1, h, 1);
      m.label.style.setProperty("--c", CSS[kind]);
    }
    arcMat.uniforms.uShow.value = state.layer === "no2" ? 1 : 0;
    opts.onLayer && opts.onLayer(state.layer, layer, state.live[state.layer] ? "live" : "snapshot");
  }
  async function loadLive(variable) {
    try {
      const res = await fetch(`${API}/scan?season=all&variable=${encodeURIComponent(variable)}`);
      const json = await res.json();
      if (!json.result) return;
      state.live[variable] = { label: state.snapshot?.layers[variable]?.label || variable, summary: json.result.summary, rows: json.result.rows };
      if (state.layer === variable) paint();
    } catch { /* keep the snapshot; the status pill says so */ }
  }
  state.snapshot = await fetch("/static/data/globe_snapshot.json").then((r) => r.json());
  state.snapshot.regions.forEach(buildMarker);
  paint();
  loadLive(state.layer);

  // ---------- hover: markers first, then countries ----------
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  let pointer = null;
  canvas.addEventListener("pointermove", (e) => { const r = canvas.getBoundingClientRect(); pointer = { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, h: r.height }; });
  canvas.addEventListener("pointerleave", () => { pointer = null; setHover(null, null); tip.hidden = true; });
  canvas.addEventListener("click", () => { if (state.hoverRegion && opts.onSelect) opts.onSelect(state.hoverRegion, state.layer); });
  function drawHighlight(c) {
    hg.clearRect(0, 0, 2048, 1024);
    if (c) { hg.fillStyle = "rgba(255,138,76,0.28)"; hg.strokeStyle = "rgba(255,170,120,0.95)"; hg.lineWidth = 2.5;
             tracePolys(hg, c.p, 2048, 1024); hg.fill("evenodd"); hg.stroke(); }
    hlTex.needsUpdate = true;
  }
  function setHover(country, regionId) {
    if (country !== state.hoverCountry) { state.hoverCountry = country; drawHighlight(country); }
    state.hoverRegion = regionId; canvas.style.cursor = regionId ? "pointer" : "grab";
  }
  function regionHere(lat, lon) {
    for (const m of markers.values()) { const [w, s, e, n] = m.region.bbox;
      if (m.group.visible && lat >= s && lat <= n && lon >= w && lon <= e) return m; }
    return null;
  }
  function updateHover() {
    if (!pointer) return;
    mouse.set((pointer.x / pointer.w) * 2 - 1, -(pointer.y / pointer.h) * 2 + 1);
    ray.setFromCamera(mouse, camera);
    const mh = ray.intersectObjects(hitTargets.filter((h) => h.parent.visible), false)[0];
    const gh = ray.intersectObject(globe, false)[0];
    if (!gh && !mh) { setHover(null, null); tip.hidden = true; return; }
    const ll = vec3ToLatLon((gh || mh).point);
    const country = gh ? countryAt(countries, ll.lat, ll.lon) : null;
    const m = mh ? markers.get(mh.object.userData.regionId) : regionHere(ll.lat, ll.lon);
    setHover(country, m ? m.region.region_id : null);
    const parts = [];
    parts.push(`<b>${country ? country.n : "Open ocean"}</b><small>${ll.lat.toFixed(1)}°, ${ll.lon.toFixed(1)}°</small>`);
    if (m) {
      const kind = kindOf(m.row);
      parts.push(`<em style="--c:${CSS[kind]}">${m.region.name}</em>`);
      parts.push(`<span>${m.row ? m.row.headline : "Not analysed for this layer."}</span><small>Click to run it live in the lab →</small>`);
    }
    tip.innerHTML = parts.join("");
    tip.hidden = false;
    const tx = Math.min(pointer.x + 18, pointer.w - tip.offsetWidth - 8), ty = Math.min(pointer.y + 18, pointer.h - tip.offsetHeight - 8);
    tip.style.transform = `translate(${tx}px, ${ty}px)`;
  }

  // ---------- layout ----------
  let shift = 0;
  function resize() {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    shift = w > 980 ? -w * (opts.shift ?? 0.2) : 0;
    camera.setViewOffset(w, h, shift, 0, w, h);
    camera.updateProjectionMatrix();
    controls.enableRotate = w > 760;          // phones: keep page scroll, globe just spins
    canvas.style.touchAction = w > 760 ? "none" : "pan-y";
  }
  new ResizeObserver(resize).observe(wrap); resize();

  // ---------- fly-to ----------
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  function flyTo(lat, lon, dist = 2.4, ms = 1800) {
    const from = camera.position.clone(), to = latLonToVec3(lat, lon, dist);
    const qa = new THREE.Quaternion().setFromUnitVectors(from.clone().normalize(), to.clone().normalize());
    const d0 = from.length();
    controls.autoRotate = false;
    state.flying = { t0: performance.now(), ms: REDUCED ? 1 : ms, from, qa, d0, d1: dist };
  }
  function setSpin(on) { state.spin = on && !REDUCED; if (!state.flying) controls.autoRotate = state.spin; }
  function setShift(f) { opts.shift = f; resize(); }

  // ---------- render loop (paused when off screen) ----------
  let visible = true, last = performance.now(), time = 0;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(wrap);
  const tmp = new THREE.Vector3(), camDir = new THREE.Vector3();
  function frame(now) {
    requestAnimationFrame(frame);
    if (!visible || document.hidden) { last = now; return; }
    const dt = Math.min(0.05, (now - last) / 1000); last = now; time += REDUCED ? 0 : dt;
    if (state.flying) {
      const f = state.flying, t = Math.min(1, Math.max(0, (now - f.t0) / f.ms)), k = ease(t);
      const qq = new THREE.Quaternion().slerp(f.qa, k);
      camera.position.copy(f.from).normalize().applyQuaternion(qq).multiplyScalar(f.d0 + (f.d1 - f.d0) * k);
      camera.lookAt(0, 0, 0);
      if (t >= 1) { state.flying = null; controls.autoRotate = state.spin; }
    } else controls.update();
    dotMat.uniforms.uTime.value = time; starMat.uniforms.uTime.value = time; arcMat.uniforms.uTime.value = time;
    stars.rotation.y = time * 0.004;
    camDir.copy(camera.position).normalize();
    const w = wrap.clientWidth, h = wrap.clientHeight;
    for (const m of markers.values()) {
      if (!m.group.visible) continue;
      m.beam.material.uniforms.uTime.value = time;
      m.rings.forEach((r) => { const p = ((time + r.userData.phase) % 1.6) / 1.6; r.scale.setScalar(1 + p * 1.8); r.material.opacity = (1 - p) * 0.9; });
      const facing = m.normal.dot(camDir);
      tmp.copy(m.normal).multiplyScalar(1.03).project(camera);
      const show = facing > 0.18;
      m.label.style.opacity = show ? Math.min(1, (facing - 0.18) * 4) : 0;
      m.label.style.pointerEvents = show ? "auto" : "none";
      const sx = ((tmp.x + 1) / 2) * w, sy = ((1 - tmp.y) / 2) * h;
      m.label.style.transform = `translate(${sx}px, ${sy}px)` + (sx > w - 200 ? " translateX(calc(-100% - 20px))" : "");
    }
    updateHover();
    renderer.render(scene, camera);
  }
  requestAnimationFrame(frame);

  return {
    flyTo, setSpin, setShift,
    setLayer(v) { if (!state.snapshot.layers[v]) return; state.layer = v; paint(); if (!state.live[v]) loadLive(v); },
    get layer() { return state.layer; },
    focusRegion(id, dist = 2.3) { const m = markers.get(id); if (m) flyTo(m.lat, m.lon, dist); },
    zoom(f) { const d = THREE.MathUtils.clamp(camera.position.length() * f, controls.minDistance, controls.maxDistance); camera.position.setLength(d); },
  };
}
