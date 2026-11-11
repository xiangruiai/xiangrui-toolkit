/* ============================================================
   ORYZO tribute rebuild — script.js
   One fixed canvas, one scroll-driven timeline, four stages.
   All code written from scratch. Vanilla JS only.
   ============================================================ */

"use strict";

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const norm = (p, a, b) => clamp((p - a) / (b - a), 0, 1);
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const finePointer = matchMedia("(pointer: fine)").matches;

// ---------- static/verify mode (?verify=1) ----------
const isVerify = new URLSearchParams(location.search).has("verify");
if (isVerify) {
  document.documentElement.classList.add("verify");
  const st = document.createElement("style");
  st.textContent = `
    html { scroll-behavior: auto !important; }
    html.verify .intro-veil, html.verify .grain,
    html.verify .cursor-dot, html.verify .cursor-ring { display: none; }
  `;
  document.head.appendChild(st);
  const sp = parseFloat(new URLSearchParams(location.search).get("scroll"));
  if (!Number.isNaN(sp)) {
    const jump = () => scrollTo(0, sp);
    if (document.readyState === "complete") jump();
    else addEventListener("load", jump, { once: true });
    setTimeout(jump, 700);
  }
}

// ============================================================
// shared cork texture
// ============================================================
const TEX = 640;
const tex = document.createElement("canvas");
tex.width = tex.height = TEX;
(function paintCork() {
  const t = tex.getContext("2d");
  const c = TEX / 2;
  const base = t.createRadialGradient(c * 0.8, c * 0.7, TEX * 0.1, c, c, TEX * 0.62);
  base.addColorStop(0, "#dca96f");
  base.addColorStop(0.55, "#c08a4e");
  base.addColorStop(1, "#96683a");
  t.fillStyle = base;
  t.fillRect(0, 0, TEX, TEX);
  for (let i = 0; i < 26; i++) {
    const x = Math.random() * TEX, y = Math.random() * TEX, r = 30 + Math.random() * 90;
    const g = t.createRadialGradient(x, y, 0, x, y, r);
    const tone = Math.random() > 0.5 ? "188,122,66" : "150,96,52";
    g.addColorStop(0, `rgba(${tone},${0.05 + Math.random() * 0.08})`);
    g.addColorStop(1, `rgba(${tone},0)`);
    t.fillStyle = g;
    t.beginPath(); t.arc(x, y, r, 0, 7); t.fill();
  }
  const tones = ["#7a4c28", "#5d3a1e", "#a06a38", "#6b452a", "#8a5c30", "#4f321a"];
  for (let i = 0; i < 3000; i++) {
    const a = Math.random() * Math.PI * 2;
    const rr = Math.sqrt(Math.random()) * (TEX * 0.485);
    t.globalAlpha = 0.12 + Math.random() * 0.45;
    t.fillStyle = tones[(Math.random() * tones.length) | 0];
    t.beginPath();
    t.arc(c + Math.cos(a) * rr, c + Math.sin(a) * rr, 0.5 + Math.random() * 1.9, 0, 7);
    t.fill();
  }
  t.globalAlpha = 1;
})();

// ============================================================
// canvas scene
// ============================================================
const canvas = document.getElementById("scene-canvas");
const ctx = canvas.getContext("2d");
const DPR = Math.min(devicePixelRatio || 1, 2);
let W = 0, H = 0;

function resize() {
  W = innerWidth; H = innerHeight;
  canvas.width = W * DPR;
  canvas.height = H * DPR;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
resize();
addEventListener("resize", () => { resize(); bakeDesk(); });

let corkPat = null;

const patCache = new WeakMap();
function patFor(g) {
  let p = patCache.get(g);
  if (!p) { p = g.createPattern(tex, "repeat"); patCache.set(g, p); }
  return p;
}

/* ---------- bowl-shaped cork coaster ---------- */
function drawBowl(g, x, y, r, squash, rot, alpha) {
  if (r < 2 || alpha <= 0.004) return;
  const sq = clamp(squash, 0.16, 1);
  const th = r * 0.38 * (1 - sq * 0.55);       // visible wall depth
  g.save();
  g.globalAlpha = alpha;
  g.translate(x, y);

  // ground shadow
  g.save();
  g.scale(1, sq);
  const sh = g.createRadialGradient(0, r * 0.55, r * 0.2, 0, r * 0.55, r * 1.25);
  sh.addColorStop(0, "rgba(0,0,0,.5)");
  sh.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = sh;
  g.beginPath(); g.arc(0, r * 0.55, r * 1.25, 0, 7); g.fill();
  g.restore();

  // wall (dark crescent under the rim)
  g.save();
  g.scale(1, sq);
  g.fillStyle = "#6e4523";
  g.beginPath(); g.arc(0, th, r, 0, 7); g.fill();
  const wallShade = g.createLinearGradient(0, -r, 0, th + r);
  wallShade.addColorStop(0, "rgba(255,225,180,.30)");
  wallShade.addColorStop(.55, "rgba(60,32,14,0)");
  wallShade.addColorStop(1, "rgba(20,8,2,.55)");
  g.fillStyle = wallShade;
  g.beginPath(); g.arc(0, th, r, 0, 7); g.fill();
  g.restore();

  // face: cork pattern, spun around the bowl axis
  g.save();
  g.scale(1, sq);
  g.rotate(rot);
  g.beginPath(); g.arc(0, 0, r, 0, 7); g.clip();
  if (!corkPat) corkPat = patFor(g);
  g.save();
  g.scale((2 * r) / TEX, (2 * r) / TEX);
  g.translate(-TEX / 2, -TEX / 2);
  g.fillStyle = corkPat;
  g.fillRect(0, 0, TEX, TEX);
  g.restore();

  // recessed interior
  g.beginPath(); g.arc(0, 0, r * 0.8, 0, 7);
  const recess = g.createRadialGradient(0, -r * 0.08, r * 0.1, 0, 0, r * 0.8);
  recess.addColorStop(0, "rgba(255,228,180,.16)");
  recess.addColorStop(.62, "rgba(70,40,18,.10)");
  recess.addColorStop(.88, "rgba(40,20,8,.52)");
  recess.addColorStop(1, "rgba(40,20,8,.72)");
  g.fillStyle = recess;
  g.fill();
  // inner top shadow (light comes from above)
  const inner = g.createRadialGradient(0, -r * 0.34, r * 0.05, 0, -r * 0.3, r * 0.95);
  inner.addColorStop(0, "rgba(30,14,5,.4)");
  inner.addColorStop(.5, "rgba(30,14,5,0)");
  g.fillStyle = inner;
  g.beginPath(); g.arc(0, 0, r * 0.8, 0, 7); g.fill();
  g.restore();

  // rim light
  g.save();
  g.scale(1, sq);
  g.lineWidth = r * 0.035;
  const rim = g.createLinearGradient(0, -r, 0, r);
  rim.addColorStop(0, "rgba(255,238,205,.55)");
  rim.addColorStop(.5, "rgba(255,238,205,.06)");
  rim.addColorStop(1, "rgba(30,14,4,.4)");
  g.strokeStyle = rim;
  g.beginPath(); g.arc(0, 0, r, 0, 7); g.stroke();
  g.restore();

  g.restore();
}

/* ---------- desk scene, baked once ---------- */
let desk = null;
function bakeDesk() {
  const DW = 1600, DH = 1000;
  desk = document.createElement("canvas");
  desk.width = DW; desk.height = DH;
  const d = desk.getContext("2d");

  // wood
  d.fillStyle = "#8a6947";
  d.fillRect(0, 0, DW, DH);
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 46; i++) {
    const y = rnd() * DH;
    const h = 6 + rnd() * 30;
    d.fillStyle = rnd() > 0.5 ? "rgba(60,40,20,.10)" : "rgba(190,150,100,.08)";
    d.fillRect(0, y, DW, h);
  }
  for (let i = 0; i < 900; i++) {
    d.fillStyle = rnd() > .5 ? "rgba(50,32,16,.08)" : "rgba(210,170,120,.06)";
    d.fillRect(rnd() * DW, rnd() * DH, 1 + rnd() * 3, 1);
  }
  // plank seams
  d.strokeStyle = "rgba(40,24,10,.22)";
  d.lineWidth = 3;
  [0.16, 0.5, 0.85].forEach((f) => {
    d.beginPath(); d.moveTo(0, DH * f); d.lineTo(DW, DH * f + 14); d.stroke();
  });

  // ---- cutting mat ----
  d.save();
  d.translate(DW * 0.54, DH * 0.48);
  d.rotate(-3.5 * Math.PI / 180);
  const MW = DW * 0.74, MH = DH * 0.96;
  // mat shadow
  d.save();
  d.shadowColor = "rgba(20,10,4,.5)";
  d.shadowBlur = 40; d.shadowOffsetY = 18;
  d.fillStyle = "#4e5e47";
  d.fillRect(-MW / 2, -MH / 2, MW, MH);
  d.restore();
  // grid
  const cell = MW / 19;
  d.strokeStyle = "rgba(210,225,190,.20)";
  d.lineWidth = 1.5;
  for (let i = 1; i < 19; i++) {
    d.beginPath(); d.moveTo(-MW / 2 + i * cell, -MH / 2); d.lineTo(-MW / 2 + i * cell, MH / 2); d.stroke();
  }
  for (let j = 1; j * cell < MH / 2; j++) {
    d.beginPath(); d.moveTo(-MW / 2, -MH / 2 + j * cell); d.lineTo(MW / 2, -MH / 2 + j * cell); d.stroke();
    d.beginPath(); d.moveTo(-MW / 2, MH / 2 - j * cell); d.lineTo(MW / 2, MH / 2 - j * cell); d.stroke();
  }
  // major lines every 5 cells
  d.strokeStyle = "rgba(210,225,190,.30)";
  d.lineWidth = 2;
  for (let i = 5; i < 19; i += 5) {
    d.beginPath(); d.moveTo(-MW / 2 + i * cell, -MH / 2); d.lineTo(-MW / 2 + i * cell, MH / 2); d.stroke();
  }
  // border + ruler numbers
  d.strokeStyle = "rgba(210,225,190,.4)";
  d.lineWidth = 2.5;
  d.strokeRect(-MW / 2, -MH / 2, MW, MH);
  d.fillStyle = "rgba(225,235,210,.75)";
  d.font = "500 15px Inter, sans-serif";
  d.textAlign = "center";
  for (let i = 1; i < 19; i++) {
    d.fillText(String(i * 10), -MW / 2 + i * cell, -MH / 2 + 30);
    d.save();
    d.translate(-MW / 2 + 26, -MH / 2 + i * cell);
    d.rotate(-Math.PI / 2);
    d.fillText(String(i * 10), 0, 0);
    d.restore();
  }
  d.restore();

  // ---- paperclip (on wood, top-left) ----
  d.save();
  d.translate(DW * 0.045, DH * 0.28);
  d.rotate(0.12);
  d.strokeStyle = "rgba(30,16,6,.3)";
  d.lineWidth = 9;
  drawClip(d, 6, 8);
  d.strokeStyle = "#c4beb2";
  d.lineWidth = 7;
  drawClip(d, 0, 0);
  d.restore();
  function drawClip(g, ox, oy) {
    g.lineCap = "round";
    g.beginPath();
    g.moveTo(26 + ox, 0 + oy);
    g.lineTo(26 + ox, 118 + oy);
    g.arc(13 + ox, 118 + oy, 13, 0, Math.PI, false);
    g.lineTo(0 + ox, 44 + oy);
    g.arc(9 + ox, 44 + oy, 9, Math.PI, 0, true);
    g.lineTo(18 + ox, 96 + oy);
    g.stroke();
  }

  // ---- pencil (on mat, top-right) ----
  d.save();
  d.translate(DW * 0.68, DH * 0.10);
  d.rotate(1.05);
  // shadow
  d.save();
  d.translate(16, 26); d.rotate(0.04);
  d.fillStyle = "rgba(20,10,4,.35)";
  rr(d, -20, -16, DW * 0.36, 32, 16); d.fill();
  d.restore();
  const PL = DW * 0.34;
  // body
  const body = d.createLinearGradient(0, -16, 0, 16);
  body.addColorStop(0, "#f2e4bd");
  body.addColorStop(.5, "#e3d0a2");
  body.addColorStop(1, "#c8b285");
  d.fillStyle = body;
  rr(d, 0, -15, PL - 46, 30, 6); d.fill();
  // facet lines
  d.strokeStyle = "rgba(120,95,55,.4)";
  d.lineWidth = 1.5;
  d.beginPath(); d.moveTo(10, -5); d.lineTo(PL - 52, -5); d.stroke();
  d.beginPath(); d.moveTo(10, 6); d.lineTo(PL - 52, 6); d.stroke();
  // wood cone + graphite
  d.fillStyle = "#dcbf90";
  d.beginPath();
  d.moveTo(PL - 46, -15); d.lineTo(PL - 6, -4); d.lineTo(PL - 6, 4); d.lineTo(PL - 46, 15);
  d.closePath(); d.fill();
  d.fillStyle = "#3c3026";
  d.beginPath();
  d.moveTo(PL - 18, -7.4); d.lineTo(PL - 2, -1.6); d.lineTo(PL - 2, 1.6); d.lineTo(PL - 18, 7.4);
  d.closePath(); d.fill();
  d.restore();

  // ---- utility knife (bottom-right, crossing the mat) ----
  d.save();
  d.translate(DW * 0.86, DH * 0.86);
  d.rotate(-0.62);
  const KL = DW * 0.34, KH = 58;
  d.save();
  d.translate(18, 30);
  d.fillStyle = "rgba(20,10,4,.4)";
  rr(d, -KL * 0.2, -KH / 2, KL, KH, 20); d.fill();
  d.restore();
  // blade
  d.fillStyle = "#cdd1d4";
  d.beginPath();
  d.moveTo(-KL * 0.2, -18); d.lineTo(-KL * 0.42, -14); d.lineTo(-KL * 0.46, 10);
  d.lineTo(-KL * 0.2, 16); d.closePath(); d.fill();
  d.strokeStyle = "rgba(90,95,100,.8)";
  d.lineWidth = 2;
  for (let i = 0; i < 4; i++) {
    d.beginPath();
    d.moveTo(-KL * (0.24 + i * 0.055), -16 + i * 1.5);
    d.lineTo(-KL * (0.28 + i * 0.055), 12 - i * 1.5);
    d.stroke();
  }
  // body
  const kb = d.createLinearGradient(0, -KH / 2, 0, KH / 2);
  kb.addColorStop(0, "#e8a53c");
  kb.addColorStop(.55, "#d28a26");
  kb.addColorStop(1, "#a96a18");
  d.fillStyle = kb;
  rr(d, -KL * 0.2, -KH / 2, KL, KH, 18); d.fill();
  // slider + grip details
  d.fillStyle = "#20150c";
  rr(d, KL * 0.16, -12, 66, 24, 8); d.fill();
  d.fillStyle = "rgba(70,40,10,.5)";
  for (let i = 0; i < 5; i++) rr(d, KL * (0.52 + i * 0.075), -KH / 2 + 6, 8, KH - 12, 4), d.fill();
  d.restore();

  // ---- the bowl coaster, baked into the desk ----
  drawBowl(d, DW * 0.535, DH * 0.475, DW * 0.155, 0.84, -0.4, 1);

  // lighting: soft key from top-left + vignette
  const key = d.createRadialGradient(DW * 0.2, DH * 0.05, 50, DW * 0.2, DH * 0.05, DW * 0.9);
  key.addColorStop(0, "rgba(255,240,205,.14)");
  key.addColorStop(1, "rgba(255,240,205,0)");
  d.fillStyle = key;
  d.fillRect(0, 0, DW, DH);
  const vig = d.createRadialGradient(DW / 2, DH / 2, DH * 0.4, DW / 2, DH / 2, DW * 0.85);
  vig.addColorStop(0, "rgba(0,0,0,0)");
  vig.addColorStop(1, "rgba(10,4,0,.36)");
  d.fillStyle = vig;
  d.fillRect(0, 0, DW, DH);
}
function rr(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}
bakeDesk();
addEventListener("load", bakeDesk);
if (document.fonts?.ready) document.fonts.ready.then(bakeDesk);

/* ============================================================
   timeline
   ============================================================ */
const track = document.querySelector(".scroll-track");
const stages = {
  intro: document.querySelector('[data-stage="intro"]'),
  features: document.querySelector('[data-stage="features"]'),
  product: document.querySelector('[data-stage="product"]'),
  contact: document.querySelector('[data-stage="contact"]'),
};
const navLinks = [...document.querySelectorAll("[data-stage-link]")];
const introLede = document.querySelector(".intro-lede");
const introStage = stages.intro;
const aiFootnote = document.querySelector(".ai-footnote");
const scrollHint = document.querySelector(".scroll-hint");
const chromaFrame = document.querySelector(".chroma-frame");
const poweredHead = document.querySelector(".product-head");
const hoverHint = document.querySelector(".hover-hint");
const gapLine = document.querySelector(".gap-line");
const portableBits = [
  document.querySelector(".portable-eyebrow"),
  document.querySelector(".wearable-line"),
  document.querySelector(".target-frame"),
];

// window helper: ramped box
function win(p, a, b, fi = 0.035, fo = 0.035) {
  return clamp(Math.min((p - a) / fi, (b - p) / fo, 1), 0, 1);
}

let scrollablePx = 1;
function measure() {
  scrollablePx = Math.max(1, track.offsetHeight - innerHeight);
}
measure();
addEventListener("resize", measure);

// pointer influence for the product stage
let px = 0.5, py = 0.5;
addEventListener("pointermove", (e) => {
  px = e.clientX / innerWidth;
  py = e.clientY / innerHeight;
});

let scrollYNow = scrollY;
addEventListener("scroll", () => { scrollYNow = scrollY; }, { passive: true });

function frame(now) {
  const p = clamp(scrollYNow / scrollablePx, 0, 1);

  // ---------- HTML stages ----------
  const wins = {
    intro: win(p, -0.05, 0.205, 0.02, 0.05),
    features: win(p, 0.245, 0.545),
    product: win(p, 0.56, 0.815),
    contact: win(p, 0.86, 1.2, 0.05, 0.1),
  };
  for (const [name, el] of Object.entries(stages)) {
    const a = wins[name];
    el.classList.toggle("is-live", a > 0.001);
    el.style.opacity = a.toFixed(3);
    if (name === "contact") el.style.pointerEvents = a > 0.5 ? "auto" : "none";
  }
  introStage.classList.toggle("is-leaving", p > 0.13);
  aiFootnote.classList.toggle("is-on", wins.features > 0.4);
  scrollHint.style.opacity = p < 0.06 ? 1 : 0;
  chromaFrame.classList.toggle("is-on", p > 0.565 && p < 0.67);
  const poweredA = win(p, 0.575, 0.675, 0.03, 0.04);
  [poweredHead, hoverHint, gapLine].forEach((el) => { if (el) el.style.opacity = poweredA.toFixed(3); });
  const portableA = win(p, 0.685, 0.815, 0.03, 0.04);
  portableBits.forEach((el) => { if (el) el.style.opacity = portableA.toFixed(3); });

  // nav active state
  let active = "intro";
  if (p > 0.84) active = "contact";
  else if (p > 0.55) active = "product";
  else if (p > 0.24) active = "features";
  navLinks.forEach((l) => l.classList.toggle("is-active", l.dataset.stageLink === active));

  // ---------- canvas ----------
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#191310";
  ctx.fillRect(0, 0, W, H);

  // desk scene: zoom toward the bowl, then fade out
  const deskA = win(p, -0.01, 0.26, 0.02, 0.07);
  if (deskA > 0) {
    const z = lerp(1, 2.05, norm(p, 0, 0.26));
    const bx = W * 0.535, by = H * 0.475;
    ctx.save();
    ctx.globalAlpha = deskA;
    ctx.translate(bx, by);
    ctx.scale(z, z);
    ctx.translate(-bx, -by);
    ctx.drawImage(desk, 0, 0, W, H);
    ctx.restore();
  }

  // amber glow on the left (product/contact)
  const amberA = win(p, 0.56, 1.2, 0.06, 0.1);
  if (amberA > 0) {
    const amb = ctx.createRadialGradient(W * 0.06, H * 0.55, 40, W * 0.06, H * 0.55, W * 0.5);
    amb.addColorStop(0, `rgba(214,126,42,${0.34 * amberA})`);
    amb.addColorStop(1, "rgba(214,126,42,0)");
    ctx.fillStyle = amb;
    ctx.fillRect(0, 0, W, H);
  }

  // ---------- the bowl across dark stages ----------
  const darkA = win(p, 0.24, 1.2, 0.05, 0.1);
  if (darkA > 0) {
    const inA = norm(p, 0.24, 0.32);
    let r = Math.min(W, H) * lerp(0.36, 0.24, norm(p, 0.32, 0.86)) * (0.7 + 0.3 * inA);
    let bx = W / 2, by = H / 2, squash = 0.88;

    if (p < 0.56) {
      // features: face-on, slow spin
      squash = 0.9;
    } else if (p < 0.685) {
      // product: tilt to the side, drift with the pointer
      squash = lerp(0.9, 0.42, norm(p, 0.56, 0.68));
      bx = W / 2 + (px - 0.5) * W * 0.06;
      by = H * 0.56 + (py - 0.5) * H * 0.08;
    } else if (p < 0.86) {
      // portable beat: hover inside the target frame
      squash = 0.5;
      by = H * 0.42 + Math.sin(now * 0.0011) * 10;
      bx = W / 2 + (px - 0.5) * W * 0.05;
    } else {
      // contact: small, bobbing above the heading
      squash = 0.6;
      const s = Math.min(1, norm(p, 0.86, 0.92));
      r *= s;
      by = H * 0.24 + Math.sin(now * 0.0012) * 12;
    }

    // dashed circle + technical frame behind the bowl during the portable beat
    if (p >= 0.66 && p < 0.86) {
      const fa = win(p, 0.66, 0.86, 0.04, 0.05);
      ctx.save();
      ctx.globalAlpha = fa;
      ctx.strokeStyle = "rgba(255,237,215,.5)";
      ctx.setLineDash([5, 7]);
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(W / 2, H * 0.5, Math.min(W, H) * 0.3, 0, 7);
      ctx.stroke();
      ctx.restore();
    }

    drawBowl(ctx, bx, by, r, squash, p * 7 + now * 0.00012, darkA);
  }

  if (!reducedMotion && !isVerify) requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
if (reducedMotion || isVerify) {
  addEventListener("scroll", () => requestAnimationFrame(() => {}), { passive: true });
  (function staticLoop() {
    // verify/reduced: redraw only on scroll events
    let last = -1;
    setInterval(() => {
      if (scrollYNow !== last) { last = scrollYNow; frame(performance.now()); }
    }, 120);
  })();
}

// ============================================================
// nav links scroll to their stage
// ============================================================
const stageScroll = { intro: 0, features: 0.3, product: 0.6, contact: 0.98 };
navLinks.forEach((l) => {
  l.addEventListener("click", (e) => {
    e.preventDefault();
    scrollTo({ top: stageScroll[l.dataset.stageLink] * scrollablePx, behavior: reducedMotion ? "auto" : "smooth" });
  });
});

// ============================================================
// header hide on scroll down
// ============================================================
const header = document.querySelector(".site-header");
let lastY = scrollY;
addEventListener("scroll", () => {
  const y = scrollY;
  header.classList.toggle("is-hidden", y > 300 && y > lastY + 4);
  lastY = y;
}, { passive: true });

// ============================================================
// custom cursor
// ============================================================
const dot = document.querySelector(".cursor-dot");
const ring = document.querySelector(".cursor-ring");
if (dot && ring && finePointer && !isVerify) {
  let mx = -100, my = -100, rx = -100, ry = -100, shown = false;
  addEventListener("pointermove", (e) => {
    mx = e.clientX; my = e.clientY;
    dot.style.transform = `translate(${mx}px, ${my}px)`;
    if (!shown) { shown = true; dot.classList.add("is-active"); ring.classList.add("is-active"); }
    const t = e.target;
    ring.classList.toggle("is-label", !!t.closest?.(".play-card"));
    ring.classList.toggle("is-link", !!t.closest?.("a, button, input"));
  });
  (function loop() {
    rx = lerp(rx, mx, 0.18);
    ry = lerp(ry, my, 0.18);
    ring.style.transform = `translate(${rx}px, ${ry}px)`;
    requestAnimationFrame(loop);
  })();
}

// ============================================================
// newsletter (fake async submit)
// ============================================================
const form = document.getElementById("footer-newsletter-form");
if (form) {
  const note = document.querySelector(".form-note");
  const btn = form.querySelector("button[type=submit]");
  const input = form.querySelector("input[type=email]");
  const lines = [
    "Noted. The coaster senses your interest.",
    "Subscribed. No emails will ever be sent.",
    "Received. Your inbox remains beautifully empty.",
  ];
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    btn.classList.add("is-loading");
    setTimeout(() => {
      btn.classList.remove("is-loading");
      note.textContent = lines[(Math.random() * lines.length) | 0];
      input.value = "";
      input.blur();
    }, 950);
  });
}

// ============================================================
// load-in
// ============================================================
const ready = () => document.body.classList.add("is-loaded");
if (document.readyState !== "loading") setTimeout(ready, 80);
else addEventListener("DOMContentLoaded", () => setTimeout(ready, 80));
