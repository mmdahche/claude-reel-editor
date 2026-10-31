#!/usr/bin/env node
// Builds index.html (the root HyperFrames composition) from:
//   <input>/shotlist.json    beats: start/end, mode A | A2 | B | C, scene + inputs, face framing,
//                            proof footage, PiP, overlays (stamp, word slam)
//   <input>/transcript.json  word-level [{text,start,end}] (hyperframes transcribe format)
//   clients/<name>/brand.json  the client's look: "tokens" for the ONE :root block in
//                            src/shell.html, "fonts", optional "grade", "cta" defaults, "audio"
//
// The kit ships no look. Every look token in src/shell.html is REQUIRED and must come from the
// brand file (DESIGN-INTERVIEW.md writes it). The build stops and lists anything still missing.
//
// Per-beat real-footage layout:
//   "layout": "split"   the beat's proof footage plays full-bleed above y 1280, face full-bleed below
//                       (an A beat's own scene is skipped for that beat)
//   "layout": "card"    A2 beat: stage split with the footage in a screen-frame card; A beat with a
//                       proof alternative: its own stage scene plays and the footage is not shown
//   (omitted)           the beat follows the --proof-split token (on = split, off = card)
//   Only beats with "proof" in mode A or A2 use it; elsewhere it is ignored with a warning.
//   Working rule unless the client says otherwise: split for the first reveal of real footage and
//   for anything the viewer must read on the phone/screen; card when the stage graphic carries the point.
//
// Free face (opt-in): a mode A or A2 beat with "face": { "free": { scale, topY, topAt, centerX?,
//   oval? } } draws a background-removed recording (VP9 WebM with alpha, see scripts/cutout/)
//   standing free on the stage instead of in the face box: no clip, no hairline, anchored to the
//   bottom of the frame. Also on a mode C "pip": { "face": { "free": ... } } (no circle or ring).
//   Beats without it build exactly as before. See freeGeom() below and WORKFLOW.md.
//
// usage: node scripts/build.mjs --input <dir> --brand clients/<name>/brand.json [--out index.html]
//        [--shotlist <file>] [--transcript <file>]   (override the two files inside --input)
//        [--cues <file>]   also write the SFX cue sheet for scripts/audio-pass.mjs
//        (--variant <file> is accepted as an old name for --brand)
//
// All media paths in shotlist.json and brand.json are relative to the project root (the kit folder).
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FPS = 30;
const W = 1080;
const H = 1920;

// ---------------------------------------------------------------- utils
function fail(msg) {
  console.error(`[build] ERROR: ${msg}`);
  process.exit(1);
}
function warn(msg) {
  console.error(`[build] warning: ${msg}`);
}
function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  if (i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--")) return process.argv[i + 1];
  return fallback;
}
function readJson(p, what) {
  try {
    return JSON.parse(readFileSync(p, "utf8"));
  } catch (err) {
    fail(`cannot read ${what} (${p}): ${err.message}`);
  }
}
const snap = (t) => Math.round(Number(t) * FPS) / FPS; // frame-quantise
const f3 = (n) => (Math.round(n * 1000) / 1000).toString();
const px = (n) => `${Math.round(n * 100) / 100}px`;
function escAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/'/g, "&#39;");
}
function escText(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function mediaPath(p, what) {
  if (!p || typeof p !== "string") fail(`${what}: missing media path`);
  if (p.startsWith("/") || p.includes("..")) fail(`${what}: media path must be inside the project (got ${p})`);
  if (!existsSync(join(ROOT, p))) fail(`${what}: file not found: ${p}`);
  return p;
}
function probeSize(p) {
  const res = spawnSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", join(ROOT, p)], { encoding: "utf8" });
  const m = (res.stdout || "").trim().match(/^(\d+),(\d+)/);
  return m ? { w: Number(m[1]), h: Number(m[2]) } : { w: W, h: H };
}

// ---------------------------------------------------------------- args + inputs
const inputDir = resolve(ROOT, arg("input", "demo-synthetic"));
const variantPath = arg("brand", "") || arg("variant", "");
if (!variantPath) fail("pass --brand clients/<name>/brand.json (the kit ships no look of its own; see DESIGN-INTERVIEW.md)");
const outPath = resolve(ROOT, arg("out", "index.html"));
const shellPath = join(ROOT, "src", "shell.html");
const shotlist = readJson(resolve(ROOT, arg("shotlist", join(inputDir, "shotlist.json"))), "shotlist.json");
let transcript = readJson(resolve(ROOT, arg("transcript", join(inputDir, "transcript.json"))), "transcript.json");
if (!Array.isArray(transcript)) transcript = Array.isArray(transcript.words) ? transcript.words : [];
transcript = transcript
  .filter((w) => w && typeof w.text === "string" && Number.isFinite(w.start) && Number.isFinite(w.end))
  .sort((a, b) => a.start - b.start);

// GSAP is loaded from the npm package (its licence does not clearly allow redistributing the file
// in this repo), copied once into assets/vendor/ (git-ignored) so renders need no network.
const gsapDest = join(ROOT, "assets", "vendor", "gsap.min.js");
if (!existsSync(gsapDest)) {
  const gsapSrc = join(ROOT, "node_modules", "gsap", "dist", "gsap.min.js");
  if (!existsSync(gsapSrc)) fail("GSAP is missing: run `npm install` in the kit folder first (it installs the pinned gsap package)");
  try {
    mkdirSync(dirname(gsapDest), { recursive: true });
    copyFileSync(gsapSrc, gsapDest);
    console.log("[build] copied node_modules/gsap/dist/gsap.min.js -> assets/vendor/gsap.min.js");
  } catch (err) {
    fail(`cannot copy GSAP into assets/vendor: ${err.message}`);
  }
}

// ---------------------------------------------------------------- tokens (ONE :root block)
let shell = readFileSync(shellPath, "utf8");
const tokRe = /\/\* @tokens:start \*\/([\s\S]*?)\/\* @tokens:end \*\//;
const tokMatch = shell.match(tokRe);
if (!tokMatch) fail("src/shell.html has no @tokens block");
let tokBlock = tokMatch[1];
const declared = new Map();
// one declaration per line; anchoring on the line start keeps "--name:" text inside comments out
for (const m of tokBlock.matchAll(/^\s*(--[a-z0-9-]+)\s*:\s*([^;\n]+);/gm)) declared.set(m[1], m[2].trim());
let variant = { name: "default", tokens: {} };
function setToken(name, value) {
  const re = new RegExp(`(^\\s*${name.replace(/[-]/g, "\\-")}\\s*:\\s*)([^;\\n]+)(;)`, "m");
  tokBlock = tokBlock.replace(re, `$1${value}$3`);
  declared.set(name, String(value));
}
const brandPath = resolve(ROOT, variantPath);
variant = readJson(brandPath, "brand file");
{
  const vt = variant.tokens || {};
  for (const [name, value] of Object.entries(vt)) {
    if (name.startsWith("//") || name.startsWith("_")) continue; // comment keys in brand.json
    if (!declared.has(name)) fail(`brand ${variantPath} sets unknown token ${name} (typo? tokens live in src/shell.html)`);
    if (/[;{}\n]/.test(String(value))) fail(`brand token ${name} has an illegal character`);
    if (String(value).trim() === "") continue; // an empty value stays REQUIRED (caught below)
    setToken(name, String(value).trim());
  }
}
// fonts: brand.json "fonts": { sans|mono|serif: { family, fallback?, system?, files?: [{ src, weight?, style? }] } }
const fontFaces = [];
{
  const fonts = variant.fonts || {};
  const FMT_OF = { ttf: "truetype", otf: "opentype", woff: "woff", woff2: "woff2" };
  const GENERIC = { sans: "sans-serif", mono: "monospace", serif: "serif" };
  for (const role of ["sans", "mono", "serif"]) {
    const f = fonts[role];
    if (!f || typeof f !== "object") continue; // --font-<role> stays REQUIRED unless tokens set it
    const family = String(f.family || "").trim();
    if (!family && f.system !== true) continue; // no family chosen yet: stays REQUIRED ("system": true = generic system font)
    const fallback = String(f.fallback || GENERIC[role]).trim();
    if (/["';{}\n]/.test(family + fallback)) fail(`brand fonts.${role}: family/fallback has an illegal character`);
    const files = Array.isArray(f.files) ? f.files : [];
    files.forEach((file, i) => {
      if (!family) fail(`brand fonts.${role}.files needs fonts.${role}.family`);
      const src = mediaPath(file && file.src, `brand fonts.${role}.files[${i}]`);
      const ext = (src.split(".").pop() || "").toLowerCase();
      if (!FMT_OF[ext]) fail(`brand fonts.${role}.files[${i}]: ${src} must be .ttf, .otf, .woff or .woff2`);
      const weight = String(file.weight || "400").replace(/[^0-9 ]/g, "") || "400";
      const style = file.style === "italic" ? "italic" : "normal";
      fontFaces.push(`@font-face {\n        font-family: "${family}";\n        src: url("${src}") format("${FMT_OF[ext]}");\n        font-weight: ${weight};\n        font-style: ${style};\n      }`);
    });
    if (family && !files.length) warn(`fonts.${role} "${family}" has no font files: the render uses whatever the machine has installed under that name (or ${fallback})`);
    setToken(`--font-${role}`, family ? `"${family}", ${fallback}` : fallback);
  }
}
// every look token must be set by now
const missing = [...declared].filter(([, v]) => v === "REQUIRED").map(([k]) => k);
if (missing.length) fail(`brand ${variantPath} leaves ${missing.length} required token(s) unset: ${missing.join(", ")}. Run DESIGN-INTERVIEW.md for this client, or fill them in brand.json.`);
// colours the scenes tint with must be #rrggbb; each gets an "-rgb" twin ("r, g, b") for rgba()
const HEX_TOKENS = ["--stage", "--stage-glow-1", "--stage-glow-2", "--line", "--pill-bg", "--accent", "--accent-ink", "--accent-text", "--text", "--text-soft", "--win", "--burn-1", "--burn-2", "--plate", "--plate-2", "--plate-ink", "--plate-muted"];
const RGB_TWINS = { "--stage": "--stage-rgb", "--line": "--line-rgb", "--text": "--text-rgb", "--accent": "--accent-rgb", "--win": "--win-rgb", "--burn-2": "--burn-rgb", "--plate-ink": "--plate-ink-rgb" };
const twinLines = [];
for (const name of HEX_TOKENS) {
  const v = declared.get(name);
  let m = /^#([0-9a-f]{6})$/i.exec(v || "");
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(v || "");
  if (!m && short) m = [v, short[1] + short[1] + short[2] + short[2] + short[3] + short[3]];
  if (!m) fail(`brand token ${name} must be a hex colour like #1a2b3c (got ${JSON.stringify(v)})`);
  if (RGB_TWINS[name]) {
    const n = parseInt(m[1], 16);
    const rgb = `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
    twinLines.push(`        ${RGB_TWINS[name]}: ${rgb};`);
    declared.set(RGB_TWINS[name], rgb);
  }
}
tokBlock = tokBlock.replace(/\n(\s*)\}\s*$/, `\n        /* derived by scripts/build.mjs from the hex tokens above */\n${twinLines.join("\n")}\n$1}\n      `);
shell = shell.replace("/* @@FONTFACE@@ */", fontFaces.length ? fontFaces.join("\n      ") : "/* no font files in this brand: system fonts */");
shell = shell.replace(tokRe, `/* @tokens:start */${tokBlock}/* @tokens:end */`);
const tok = (name) => declared.get(name);
const captionStyle = tok("--caption-style") === "bigword" ? "bigword" : "pill";
const maxWords = Math.max(1, Math.min(4, parseInt(tok("--caption-max-words"), 10) || 3));
const proofSplit = tok("--proof-split") !== "off";
const gradeIntensity = Math.max(0, Math.min(1, parseFloat(tok("--grade-intensity")) || 0));
// the footage grade is part of the look, so it lives in the brand file ("grade": a HyperFrames
// data-color-grading payload without "intensity"; the --grade-intensity token sets the strength)
const gradeDef = variant.grade && typeof variant.grade === "object" ? variant.grade : null;
if (gradeIntensity > 0 && (!gradeDef || !Object.keys(gradeDef).filter((k) => !k.startsWith("//") && !k.startsWith("_")).length)) {
  fail(`brand ${variantPath} sets --grade-intensity ${gradeIntensity} but has no "grade" block (set --grade-intensity to 0 for ungraded footage)`);
}
// client defaults for the closing scenes (brand.json "cta": dmName, dmAvatar, footerLogo, footerText, coverLogo)
const brandCta = variant.cta && typeof variant.cta === "object" ? variant.cta : {};
for (const k of ["dmAvatar", "footerLogo", "coverLogo"]) if (brandCta[k]) mediaPath(brandCta[k], `brand cta.${k}`);
const captionMaxW = parseFloat(tok("--caption-max-w")) || 780;
// PiP circle position/diameter (tokens --pip-x/-y/-size; defaults are the original 60 / 1500 / 320)
const tokNum = (name, fallback) => {
  const n = parseFloat(tok(name));
  return Number.isFinite(n) ? n : fallback;
};
const pipX = tokNum("--pip-x", 60);
const pipY = tokNum("--pip-y", 1500);
const pipSize = tokNum("--pip-size", 320);
if (!(pipSize >= 120 && pipSize <= 600)) fail(`--pip-size ${pipSize}px is outside 120-600px`);
if (pipX < 0 || pipY < 0 || pipX + pipSize > W || pipY + pipSize > H) fail(`the PiP circle (--pip-x/-y/-size) must fit on the 1080x1920 canvas`);

// ---------------------------------------------------------------- shotlist validation
const rec = shotlist.recording || {};
const recSrc = mediaPath(rec.src, "recording");
const recSize = probeSize(recSrc);
const recOffset = Number(rec.offset) || 0;
const recEye = { x: Number(rec.eyeX ?? 0.5), y: Number(rec.eyeY ?? 0.33) };
const recGrade = rec.grade !== false;
const captures = shotlist.captures || {};
const beats = (shotlist.beats || []).map((b, i) => ({ ...b, idx: i, start: snap(b.start), end: snap(b.end) }));
if (!beats.length) fail("shotlist has no beats");
const D = snap(shotlist.duration ?? beats[beats.length - 1].end);
const MODES = new Set(["A", "A2", "B", "C"]);
const ids = new Set();
beats.forEach((b, i) => {
  if (!b.id || !/^[a-z0-9-]+$/i.test(b.id)) fail(`beat ${i} needs an id of letters/digits/dashes`);
  if (ids.has(b.id)) fail(`duplicate beat id ${b.id}`);
  ids.add(b.id);
  if (!MODES.has(b.mode)) fail(`beat ${b.id}: mode must be A, A2, B or C`);
  if (!(b.end > b.start)) fail(`beat ${b.id}: end must be after start`);
  const prevEnd = i === 0 ? 0 : beats[i - 1].end;
  if (Math.abs(b.start - prevEnd) > 1 / FPS / 2) fail(`beat ${b.id}: starts at ${b.start}, previous ends at ${prevEnd} (beats must be back to back)`);
  if (b.mode === "A2" && !b.proof) fail(`beat ${b.id}: mode A2 needs a proof {capture, at}`);
  if (b.scene && !existsSync(join(ROOT, "compositions", `${b.scene.type}.html`))) fail(`beat ${b.id}: unknown scene ${b.scene.type}`);
  if (b.proof) {
    const cap = captures[b.proof.capture];
    if (!cap) fail(`beat ${b.id}: proof capture "${b.proof.capture}" not in shotlist.captures`);
    mediaPath(cap.src, `capture ${b.proof.capture}`);
  }
  if (b.layout !== undefined) {
    if (b.layout !== "card" && b.layout !== "split") fail(`beat ${b.id}: layout must be "card" or "split" (got ${JSON.stringify(b.layout)})`);
    if (!b.proof || !["A", "A2"].includes(b.mode)) warn(`beat ${b.id}: layout only applies to mode A/A2 beats with proof footage (ignored)`);
  }
  if (b.ownAudio !== undefined && typeof b.ownAudio !== "boolean") fail(`beat ${b.id}: ownAudio must be true or false`);
  if (b.ownAudio === true) {
    const spoken = transcript.filter((w) => w.start >= b.start && w.start < b.end).length;
    if (spoken) warn(`beat ${b.id}: ownAudio beat has ${spoken} transcript word(s) inside it (they still get captions, and the audio pass treats that span as not-voice)`);
  }
});
if (Math.abs(beats[beats.length - 1].end - D) > 1 / FPS / 2) fail(`last beat ends at ${beats[beats.length - 1].end} but duration is ${D}`);

// declared variables per scene file -> warn on unknown inputs (defaults kept for the SFX cue sheet)
const sceneVars = new Map();
const sceneDefaults = new Map();
function varsOf(type) {
  if (!sceneVars.has(type)) {
    const html = readFileSync(join(ROOT, "compositions", `${type}.html`), "utf8");
    const m = html.match(/data-composition-variables='([\s\S]*?)'/);
    let decl = [];
    try {
      decl = m ? JSON.parse(m[1]) : [];
    } catch (err) {
      warn(`${type}.html variable declarations do not parse: ${err.message}`);
    }
    sceneVars.set(type, new Set(decl.map((v) => v.id)));
    sceneDefaults.set(type, Object.fromEntries(decl.map((v) => [v.id, v.default])));
  }
  return sceneVars.get(type);
}
// the values a scene actually sees at runtime: its declared defaults, overridden by the inputs
function effectiveVars(type, inputs, extra) {
  varsOf(type);
  return { ...sceneDefaults.get(type), ...(inputs || {}), ...(extra || {}) };
}
function sceneValues(type, inputs, extra) {
  const known = varsOf(type);
  const out = {};
  for (const [k, v] of Object.entries({ ...(inputs || {}), ...(extra || {}) })) {
    if (!known.has(k)) warn(`scene ${type}: input "${k}" is not a declared variable (ignored by the scene)`);
    out[k] = v !== null && typeof v === "object" ? JSON.stringify(v) : v;
  }
  return out;
}

// ---------------------------------------------------------------- effective modes
// Per beat: "layout": "split" plays a beat that carries `proof` as the
// documentary split (footage full-bleed top, face full-bleed bottom); "layout": "card" sends an
// authored A2 beat back to the stage split with the footage in a screen-frame card and lets an
// A beat keep its own scene. A beat without "layout" follows the --proof-split token.
beats.forEach((b) => {
  b.eff = b.mode;
  b.fallbackFrame = false;
  const split = b.layout === "split" || (b.layout !== "card" && proofSplit);
  if (b.mode === "A2" && !split) {
    b.eff = "A";
    b.fallbackFrame = true;
  } else if (b.mode === "A" && b.proof && split) {
    b.eff = "A2";
    b.sceneSuppressed = true;
  }
});
beats.forEach((b, i) => {
  if (b.sceneSuppressed && beats[i + 1] && beats[i + 1].scene && beats[i + 1].scene.continue) {
    fail(`beat ${b.id}: a beat whose scene continues into the next beat cannot also carry a proof alternative`);
  }
});

// ---------------------------------------------------------------- scene instances
// the closing scenes take the client's handle, avatar and footer from brand.json unless the beat sets them
const BRAND_KEYS = { cta: ["dmName", "dmAvatar", "footerLogo", "footerText", "coverLogo"], "cta-footer": ["footerLogo", "footerText"] };
function withBrandDefaults(type, inputs) {
  const keys = BRAND_KEYS[type];
  if (!keys) return inputs;
  const out = { ...inputs };
  for (const k of keys) if (out[k] === undefined && brandCta[k] !== undefined && brandCta[k] !== "") out[k] = brandCta[k];
  return out;
}
const instances = [];
let hookPersistEnd = 0;
beats.forEach((b) => {
  if (!b.scene || b.sceneSuppressed) return;
  if (b.scene.continue) {
    const prev = instances[instances.length - 1];
    if (!prev || prev.type !== b.scene.type || Math.abs(prev.end - b.start) > 1e-6) fail(`beat ${b.id}: scene.continue needs the previous beat to end with the same scene type`);
    prev.end = b.end;
    return;
  }
  const inst = { type: b.scene.type, inputs: withBrandDefaults(b.scene.type, b.scene.inputs || {}), start: b.start, end: b.end, beat: b.id, extra: {}, media: b.scene.media || null };
  if (inst.media) {
    if (inst.type !== "screen-frame") fail(`beat ${b.id}: scene.media is only supported on screen-frame`);
    const cap = captures[inst.media.capture];
    if (!cap) fail(`beat ${b.id}: scene.media capture "${inst.media.capture}" not in shotlist.captures`);
    mediaPath(cap.src, `capture ${inst.media.capture}`);
  }
  const persist = Number(b.scene.persist) || 0;
  if (persist > 0) {
    inst.end = Math.min(D, snap(b.end + persist));
    inst.extra.persistAt = f3(b.end - b.start);
    hookPersistEnd = Math.max(hookPersistEnd, inst.end);
  }
  instances.push(inst);
});

// ---------------------------------------------------------------- face geometry
const FACE_BOX = {
  A: { x: 40, y: 1400, w: 1000, h: 480, ex: 540, ey: 1575, base: 0, round: true },
  A2: { x: 0, y: 1280, w: 1080, h: 640, ex: 540, ey: 1520, base: 0, round: false },
  B: { x: 0, y: 0, w: 1080, h: 1920, ex: 540, ey: 700, base: 1.0, round: false },
  // eye point and base scale keep the original 320px proportions (eye 132px down, 0.5x) at any size
  PIP: { x: pipX, y: pipY, w: pipSize, h: pipSize, ex: pipX + pipSize / 2, ey: pipY + (pipSize * 132) / 320, base: (0.5 * pipSize) / 320, circle: true },
};
function faceGeom(kind, face) {
  const box = FACE_BOX[kind];
  const eye = { x: Number(face?.eyeX ?? recEye.x), y: Number(face?.eyeY ?? recEye.y) };
  const zoom = Math.max(0.5, Math.min(3, Number(face?.zoom ?? 1)));
  const cover = Math.max(box.w / recSize.w, box.h / recSize.h);
  const s = Math.max(cover, box.base || cover) * zoom;
  if (s > recSize.w / W + 1e-6 && !box.circle) {
    warn(`${kind} face crop scales the recording ${s.toFixed(2)}x (upscaling past its native size; keep zoom <= 1 or record at 1080x1920+)`);
  }
  const w = recSize.w * s;
  const h = recSize.h * s;
  let left = box.ex - eye.x * w;
  let top = box.ey - eye.y * h;
  left = Math.min(box.x, Math.max(box.x + box.w - w, left));
  top = Math.min(box.y, Math.max(box.y + box.h - h, top));
  let clip;
  if (box.circle) {
    const r = box.w / 2;
    clip = `circle(${px(r)} at ${px(box.x + r - left)} ${px(box.y + r - top)})`;
  } else {
    const t = box.y - top;
    const rgt = left + w - (box.x + box.w);
    const btm = top + h - (box.y + box.h);
    const l = box.x - left;
    clip = `inset(${px(t)} ${px(rgt)} ${px(btm)} ${px(l)}${box.round ? " round var(--face-radius)" : ""})`;
  }
  return { left, top, w, h, clip, box };
}
// Free face (opt-in): the cutout at `scale`, with recording point (centerX, topY)
// placed on canvas (540, topAt). topY is the highest hair point of that run in the recording
// (0-1 of its height), measured outside the build, so topAt is where the top of the hair lands.
// Optional "oval": { cy, cx?, rx?, ry?, inner? } (recording fractions; defaults cx 0.5, rx 0.5,
// ry 0.75, inner 0.7) fades the cutout outside an ellipse: fully solid inside `inner` of the
// radii, transparent at the ellipse. It tapers the shoulders where the recording's own frame cuts
// them off, so they melt into the stage instead of ending in a straight line. Keep the head inside
// the solid part (measure it; the build cannot see the pixels).
const freeNotes = [];
function freeGeom(face, id) {
  const f = face && face.free;
  const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
  if (!isObj(f)) fail(`face run ${id}: face.free must be an object {scale, topY, topAt, centerX?, oval?}`);
  const numOf = (o, path, k, lo, hi, def) => {
    const v = o[k] === undefined ? def : Number(o[k]);
    if (!Number.isFinite(v) || v < lo || v > hi) fail(`face run ${id}: ${path}.${k} must be a number from ${lo} to ${hi} (got ${JSON.stringify(o[k])})`);
    return v;
  };
  const num = (k, lo, hi, def) => numOf(f, "face.free", k, lo, hi, def);
  const s = num("scale", 0.2, 2);
  const cx = num("centerX", 0, 1, recEye.x);
  const topY = num("topY", 0, 1);
  const topAt = num("topAt", 0, H);
  const w = recSize.w * s;
  const h = recSize.h * s;
  const left = 540 - cx * w;
  const top = topAt - topY * h;
  if (top + h < H - 0.5) fail(`face run ${id}: the free cutout's bottom edge lands at y ${Math.round(top + h)}, above the bottom of the frame (raise scale or topAt)`);
  const captionY = tokNum("--caption-y", 1280);
  if (topAt < captionY) warn(`face run ${id}: the free cutout's hair top (y ${Math.round(topAt)}) rises ${Math.round(captionY - topAt)}px above the caption line (y ${captionY})`);
  let mask = "";
  if (f.oval !== undefined) {
    if (!isObj(f.oval)) fail(`face run ${id}: face.free.oval must be an object {cy, cx?, rx?, ry?, inner?}`);
    const o = (k, lo, hi, def) => numOf(f.oval, "face.free.oval", k, lo, hi, def);
    const ov = { cx: o("cx", 0, 1, 0.5), cy: o("cy", 0, 1), rx: o("rx", 0.1, 2, 0.5), ry: o("ry", 0.1, 2, 0.75), inner: o("inner", 0, 0.99, 0.7) };
    const pct = (n) => `${Math.round(n * 10000) / 100}%`;
    mask = `radial-gradient(ellipse ${pct(ov.rx)} ${pct(ov.ry)} at ${pct(ov.cx)} ${pct(ov.cy)}, #000 ${pct(ov.inner)}, transparent 100%)`;
  } else if (left > 0.5 || left + w < W - 0.5) {
    warn(`face run ${id}: the recording's own left/right edges fall inside the frame (x ${Math.round(left)} and ${Math.round(left + w)}), so cut-off shoulders end in straight lines; face.free.oval tapers them`);
  }
  freeNotes.push(`${id} scale ${s} at x ${Math.round(left)}-${Math.round(left + w)}, hair top y ${Math.round(topAt)}, bottom y ${Math.round(top + h)}${mask ? ", oval shoulder fade" : ""}`);
  return { left, top, w, h, mask, topAt };
}
// The recording above the hair is empty (transparent), but the layout checker reads the video's
// whole rectangle as covering whatever is behind it (e.g. a table's last row). The free face keeps
// FREE_HEADROOM px above topAt and trims only the empty area above that, so the element box matches
// what is visible. topAt is the run's highest hair point, so the trim never touches the
// person (measure topY on every frame of the run so no visible pixel sits above the trim line).
const FREE_HEADROOM = 40;
// a free face needs a recording with real alpha (VP9 WebM, alpha_mode=1); warn once if it has none
let alphaChecked = false;
function checkRecordingAlpha() {
  if (alphaChecked) return;
  alphaChecked = true;
  const res = spawnSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream_tags=alpha_mode", "-of", "csv=p=0", join(ROOT, recSrc)], { encoding: "utf8" });
  if (res.error || (res.stdout || "").trim() !== "1") warn(`free face: the recording ${recSrc} does not report alpha_mode=1, so the "free" cutout will show its whole rectangle (use a background-removed WebM)`);
}
function gradeAttr(enabled) {
  if (!enabled || gradeIntensity <= 0) return "";
  const clean = Object.fromEntries(Object.entries(gradeDef).filter(([k]) => !k.startsWith("//") && !k.startsWith("_")));
  const payload = { ...clean, intensity: gradeIntensity };
  return ` data-color-grading="${escAttr(JSON.stringify(payload))}"`;
}

// ---------------------------------------------------------------- layers
const layers = [];
const tlLines = [];
const counts = { scenes: 0, faces: 0, plates: 0, captions: 0, overlays: 0 };

layers.push(
  `<div id="stage" class="layer" data-composition-id="stage-bg" data-composition-src="compositions/stage-bg.html" data-start="0" data-duration="${f3(D)}" data-track-index="0" data-width="1080" data-height="1920" style="height:1920px;z-index:0" data-variable-values="${escAttr(JSON.stringify({ span: D }))}"></div>`,
);

// scene hosts (panel 1080 x 1440 at the top in A and C)
instances.forEach((inst) => {
  const span = inst.end - inst.start;
  if (inst.media) {
    // place the footage at root level inside the frame's screen rect (seek-safe media timing)
    const cap = captures[inst.media.capture];
    const phone = inst.inputs.device === "phone";
    const top = Number(inst.media.top) || 330;
    const sh = Math.min(1130, Number(inst.media.bottom) || (phone ? 1040 : 1100)) - top;
    const aspect = phone ? 0.46 : Number(inst.media.frameAspect) || 0.8;
    const sw = Math.min(phone ? 420 : 780, Math.round(sh * aspect));
    // optional media.centerX moves the frame sideways (e.g. to clear a lifted PiP); default centred
    const cx = inst.media.centerX == null ? 540 : Number(inst.media.centerX);
    if (!Number.isFinite(cx) || cx - sw / 2 < 0 || cx + sw / 2 > W) fail(`beat ${inst.beat}: media.centerX ${inst.media.centerX} puts the ${sw}px frame off the canvas`);
    const rect = { x: Math.round(cx - sw / 2), y: top, w: sw, h: sh };
    inst.extra = { ...inst.extra, screenX: rect.x, screenY: rect.y, screenW: rect.w, screenH: rect.h };
    const enterAt = Number(inst.inputs.enterAt ?? 0.05);
    const pos = `${Math.round(Number(inst.media.focusX ?? 0.5) * 100)}% ${Math.round(Number(inst.media.focusY ?? 0.5) * 100)}%`;
    const radius = phone ? "54px" : "calc(var(--card-radius) - 2px)";
    layers.push(
      `<div id="sfm-${inst.beat}" class="media-wrap" style="left:${rect.x}px;top:${rect.y}px;width:${rect.w}px;height:${rect.h}px;border-radius:${radius};z-index:12"><video id="sfmv-${inst.beat}" class="fill" src="${escAttr(cap.src)}" muted playsinline data-start="${f3(inst.start)}" data-duration="${f3(span)}" data-media-start="${f3(Math.max(0, Number(inst.media.at) || 0))}" data-track-index="12" style="object-position:${pos}"${gradeAttr(cap.grade !== false)}></video></div>`,
    );
    tlLines.push(`tl.fromTo("#sfm-${inst.beat}", { y: 60, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, ${f3(inst.start + enterAt)});`);
    counts.plates++;
  }
  const values = sceneValues(inst.type, inst.inputs, { span: f3(span), ...inst.extra });
  layers.push(
    `<div id="sc-${inst.beat}" class="layer" data-composition-id="${inst.type}-${inst.beat}" data-composition-src="compositions/${inst.type}.html" data-start="${f3(inst.start)}" data-duration="${f3(span)}" data-track-index="2" data-width="1080" data-height="1440" style="height:1440px;z-index:10" data-variable-values="${escAttr(JSON.stringify(values))}"></div>`,
  );
  counts.scenes++;
});

// proof footage: documentary plate (A2) or screen-frame card (A fallback)
beats.forEach((b) => {
  if (!b.proof) return;
  if (b.eff !== "A2" && !b.fallbackFrame) return;
  const cap = captures[b.proof.capture];
  const dur = b.end - b.start;
  const at = Math.max(0, Number(b.proof.at) || 0);
  const pos = `${Math.round((Number(b.proof.focusX ?? 0.5)) * 100)}% ${Math.round((Number(b.proof.focusY ?? 0.5)) * 100)}%`;
  const grade = gradeAttr(cap.grade !== false);
  if (b.eff === "A2") {
    layers.push(
      `<div id="plate-${b.id}" class="media-wrap" style="left:0;top:0;width:1080px;height:1280px;z-index:5"><video id="platev-${b.id}" class="fill" src="${escAttr(cap.src)}" muted playsinline data-start="${f3(b.start)}" data-duration="${f3(dur)}" data-media-start="${f3(at)}" data-track-index="5" style="object-position:${pos}"${grade}></video></div>`,
    );
    counts.plates++;
    if (b.proof.label) {
      layers.push(
        `<div id="tag-${b.id}" class="clip proof-tag-pill" data-start="${f3(b.start)}" data-duration="${f3(dur)}" data-track-index="28" style="left:var(--safe-left);top:1140px;z-index:28"><i class="proof-tag-dot"></i><span>${escText(b.proof.label)}</span></div>`,
      );
      tlLines.push(`tl.fromTo("#tag-${b.id}", { scale: 0.92, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.12, ease: "power2.out" }, ${f3(b.start + 0.1)});`);
    }
  } else {
    // fallback: card in the panel, under a persisting hook title if there is one
    const clearTop = hookPersistEnd > b.start ? 600 : 330;
    const aspect = Number(b.proof.frameAspect) || 0.8;
    const sh = 1150 - clearTop;
    const sw = Math.min(780, Math.round(sh * aspect));
    const sx = Math.round(540 - sw / 2);
    const sy = clearTop;
    const enterAt = 0.05;
    const values = sceneValues("screen-frame", { device: "card", lightPlate: false, label: "" }, { screenX: sx, screenY: sy, screenW: sw, screenH: sh, enterAt, span: f3(dur) });
    layers.push(
      `<div id="sc-${b.id}" class="layer" data-composition-id="screen-frame-${b.id}" data-composition-src="compositions/screen-frame.html" data-start="${f3(b.start)}" data-duration="${f3(dur)}" data-track-index="2" data-width="1080" data-height="1440" style="height:1440px;z-index:10" data-variable-values="${escAttr(JSON.stringify(values))}"></div>`,
    );
    layers.push(
      `<div id="sfm-${b.id}" class="media-wrap" style="left:${sx}px;top:${sy}px;width:${sw}px;height:${sh}px;border-radius:calc(var(--card-radius) - 2px);z-index:12"><video id="sfmv-${b.id}" class="fill" src="${escAttr(cap.src)}" muted playsinline data-start="${f3(b.start)}" data-duration="${f3(dur)}" data-media-start="${f3(at)}" data-track-index="12" style="object-position:${pos}"${grade}></video></div>`,
    );
    tlLines.push(`tl.fromTo("#sfm-${b.id}", { y: 60, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, ${f3(b.start + enterAt)});`);
    if (b.proof.label) {
      layers.push(
        `<div id="tag-${b.id}" class="clip proof-tag-pill" data-start="${f3(b.start)}" data-duration="${f3(dur)}" data-track-index="28" style="left:${sx + 24}px;top:${sy + 24}px;z-index:28"><i class="proof-tag-dot"></i><span>${escText(b.proof.label)}</span></div>`,
      );
      tlLines.push(`tl.fromTo("#tag-${b.id}", { scale: 0.92, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.12, ease: "power2.out" }, ${f3(b.start + 0.4)});`);
    }
    counts.scenes++;
    counts.plates++;
  }
});

// face: one clip per run of beats with the same mode + framing (hard cuts between modes)
const faceRuns = [];
beats.forEach((b) => {
  if (!["A", "A2", "B"].includes(b.eff)) return;
  const key = `${b.eff}|${JSON.stringify(b.face || {})}`;
  const last = faceRuns[faceRuns.length - 1];
  if (last && last.key === key && Math.abs(last.end - b.start) < 1e-6) last.end = b.end;
  else faceRuns.push({ key, kind: b.eff, face: b.face, start: b.start, end: b.end, id: b.id });
});
// "face": { "grade": false } leaves that run ungraded (a stretch of the recording that is not the
// camera face, e.g. finished footage cut into face.mp4); the recording's own grade flag still wins
const faceGraded = (face) => recGrade && !(face && face.grade === false);
// free face (opt-in): an untimed wrapper carries the position and the oval fade, the timed video
// fills it (the renderer swaps the video for a frame image inside the same parent, as with the PiP)
function freeFaceHtml(wrapId, vidId, start, dur, face, label, z) {
  checkRecordingAlpha();
  const g = freeGeom(face, label);
  const maskCss = g.mask ? `;-webkit-mask-image:${g.mask};mask-image:${g.mask}` : "";
  const trim = Math.max(0, g.topAt - FREE_HEADROOM - g.top);
  return `<div id="${wrapId}" style="position:absolute;left:${px(g.left)};top:${px(g.top)};width:${px(g.w)};height:${px(g.h)};z-index:${z}${maskCss}"><video id="${vidId}" class="face" src="${escAttr(recSrc)}" muted playsinline data-start="${f3(start)}" data-duration="${f3(dur)}" data-media-start="${f3(start + recOffset)}" data-track-index="${z}" style="left:0px;top:0px;width:${px(g.w)};height:${px(g.h)};clip-path:inset(${px(trim)} 0px 0px 0px)"${gradeAttr(faceGraded(face))}></video></div>`;
}
faceRuns.forEach((r) => {
  const dur = r.end - r.start;
  if (r.face && r.face.free !== undefined) {
    // mode A (stage split) and A2 (proof split): no box, no seam crop; B is full frame already
    if (r.kind !== "A" && r.kind !== "A2") fail(`face run ${r.id}: face.free is only for mode A and A2 beats (this run is ${r.kind})`);
    layers.push(freeFaceHtml(`facew-${r.id}`, `face-${r.id}`, r.start, dur, r.face, r.id, 20));
    counts.faces++;
    return;
  }
  const g = faceGeom(r.kind, r.face);
  layers.push(
    `<video id="face-${r.id}" class="face" src="${escAttr(recSrc)}" muted playsinline data-start="${f3(r.start)}" data-duration="${f3(dur)}" data-media-start="${f3(r.start + recOffset)}" data-track-index="20" style="left:${px(g.left)};top:${px(g.top)};width:${px(g.w)};height:${px(g.h)};clip-path:${g.clip};z-index:20"${gradeAttr(faceGraded(r.face))}></video>`,
  );
  if (r.kind === "A") {
    layers.push(
      `<div id="hair-${r.id}" class="clip face-hair" data-start="${f3(r.start)}" data-duration="${f3(dur)}" data-track-index="21" style="left:${g.box.x}px;top:${g.box.y}px;width:${g.box.w}px;height:${g.box.h}px;z-index:21"></div>`,
    );
  }
  counts.faces++;
});

// picture-in-picture (mode C only): circle at --pip-x/-y, --pip-size across (default 320px at
// x 60, y 1500). "pip": { "continue": true } carries the previous beat's circle on through this
// beat (one clip, no second pop), like scene.continue; it needs that circle to run to this
// beat's start and keeps its framing.
const pips = [];
beats.forEach((b) => {
  if (!b.pip) return;
  if (b.eff !== "C") warn(`beat ${b.id}: pip is meant for mode C`);
  const s = snap(b.pip.start ?? b.start);
  const e = snap(Math.min(b.end, b.pip.end ?? b.end));
  if (!(e > s)) fail(`beat ${b.id}: pip end must be after start`);
  if (b.pip.continue) {
    const prev = pips[pips.length - 1];
    if (!prev || Math.abs(prev.e - b.start) > 1e-6 || Math.abs(s - b.start) > 1e-6) fail(`beat ${b.id}: pip.continue needs the previous beat's pip to run to this beat's start, and this one to start there`);
    if (b.pip.face && JSON.stringify(b.pip.face) !== JSON.stringify(prev.face || {})) fail(`beat ${b.id}: pip.continue keeps the previous pip's framing (leave pip.face out or match it)`);
    prev.e = e;
    prev.beatEnd = b.end;
    return;
  }
  pips.push({ id: b.id, s, e, beatEnd: b.end, face: b.pip.face || b.face });
});
pips.forEach((p) => {
  const dur = p.e - p.s;
  if (p.face && p.face.free !== undefined) {
    // "pip": { "face": { "free": {...} } } (opt-in): the free cutout instead of the circle and ring;
    // same timing and the same pop in/out below (they target the wrapper id)
    layers.push(freeFaceHtml(`pipw-${p.id}`, `pip-${p.id}`, p.s, dur, p.face, `pip ${p.id}`, 25));
  } else {
    const g = faceGeom("PIP", p.face);
    layers.push(
      `<div id="pipw-${p.id}" class="pip-wrap" style="z-index:25"><video id="pip-${p.id}" class="face" src="${escAttr(recSrc)}" muted playsinline data-start="${f3(p.s)}" data-duration="${f3(dur)}" data-media-start="${f3(p.s + recOffset)}" data-track-index="25" style="left:${px(g.left - pipX)};top:${px(g.top - pipY)};width:${px(g.w)};height:${px(g.h)};clip-path:${g.clip}"${gradeAttr(faceGraded(p.face))}></video><div id="pipr-${p.id}" class="clip pip-ring" data-start="${f3(p.s)}" data-duration="${f3(dur)}" data-track-index="26"></div></div>`,
    );
  }
  tlLines.push(`tl.fromTo("#pipw-${p.id}", { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(1.8)" }, ${f3(p.s)});`);
  if (p.e < p.beatEnd - 0.05) tlLines.push(`tl.to("#pipw-${p.id}", { scale: 0.6, opacity: 0, duration: 0.2, ease: "power2.in" }, ${f3(p.e - 0.2)});`);
  counts.faces++;
});

// overlays: stamp (panel 1080 x 1440) and word slam (full canvas, on the caption line)
const slamWindows = [];
const overlayList = []; // for the SFX cue sheet
beats.forEach((b) => {
  (b.overlays || []).forEach((o, k) => {
    const type = o.type;
    if (!existsSync(join(ROOT, "compositions", `${type}.html`))) fail(`beat ${b.id}: unknown overlay ${type}`);
    const s = snap(o.at ?? b.start);
    const e = snap(Math.min(D, o.end ?? b.end));
    if (!(e > s)) fail(`beat ${b.id}: overlay ${type} end must be after start`);
    const full = type === "word-slam";
    const values = sceneValues(type, withBrandDefaults(type, o.inputs || {}), { span: f3(e - s) });
    const h = full ? 1920 : 1440;
    layers.push(
      `<div id="ov-${b.id}-${k}" class="layer" data-composition-id="${type}-${b.id}-${k}" data-composition-src="compositions/${type}.html" data-start="${f3(s)}" data-duration="${f3(e - s)}" data-track-index="30" data-width="1080" data-height="${h}" style="height:${h}px;z-index:${full ? 45 : 30}" data-variable-values="${escAttr(JSON.stringify(values))}"></div>`,
    );
    if (full) slamWindows.push([s, e]);
    overlayList.push({ type, start: s, end: e, inputs: o.inputs || {}, beat: b.id });
    counts.overlays++;
  });
});

// ---------------------------------------------------------------- captions
// Heavy-sans caps advance widths (em), for sizing big-word captions to --caption-max-w. Measured on
// one common grotesque at 900; other brand fonts land close enough because the size is capped and
// the build never goes below 56px. If a brand font runs wide, lower --bigword-size.
const CAPW = { A: 0.74, B: 0.7, C: 0.72, D: 0.74, E: 0.62, F: 0.6, G: 0.76, H: 0.76, I: 0.31, J: 0.58, K: 0.72, L: 0.58, M: 0.9, N: 0.76, O: 0.78, P: 0.68, Q: 0.78, R: 0.7, S: 0.66, T: 0.64, U: 0.74, V: 0.72, W: 1.0, X: 0.72, Y: 0.7, Z: 0.64, " ": 0.26 };
const emWidth = (s) => Array.from(s.toUpperCase()).reduce((a, ch) => a + (CAPW[ch] ?? (/[0-9]/.test(ch) ? 0.66 : 0.34)) - 0.035, 0);
const beatOf = (t) => beats.find((b) => t >= b.start && t < b.end) || beats[beats.length - 1];
const cleanWord = (s) => s.replace(/^["'“‘(]+|["'”’)]+$/g, "");
const display = (words) => words.map((w) => cleanWord(w.text)).join(" ").replace(/[,.;:]+$/, "");

const WEAK = new Set(["a", "an", "the", "to", "of", "and", "or", "but", "for", "in", "on", "at", "is", "i", "your", "my", "with", "so"]);
const groups = [];
let cur = [];
const flush = () => {
  if (cur.length) groups.push(cur);
  cur = [];
};
transcript.forEach((w, i) => {
  const next = transcript[i + 1];
  cur.push(w);
  const gap = next ? next.start - w.end : 99;
  const sameBeat = next && beatOf((next.start + next.end) / 2) === beatOf((w.start + w.end) / 2);
  // captions may cross a mode cut: the line never moves, so a phrase reads straight through
  let brk = !next;
  if (captionStyle === "bigword") {
    // one word per caption, but keep adding the next word while this caption would be on
    // screen for under 0.25s (fast function words), as long as the pair still fits one line
    const onScreen = next ? next.start - cur[0].start : 99;
    const merged = display([...cur, ...(next ? [next] : [])]);
    if (!(next && sameBeat && onScreen < 0.25 && gap < 0.15 && cur.length < 3 && merged.length <= 12)) brk = true;
  } else {
    const chars = display(cur).length + (next ? cleanWord(next.text).length + 1 : 0);
    const natural = /[.?!]$/.test(w.text) || (/,$/.test(w.text) && gap > 0.15) || gap > 0.35;
    const full = cur.length >= maxWords || chars > 26;
    if (natural) brk = true;
    else if (full && next) {
      // a group that is merely full should not end on a weak word ("You talk to"):
      // carry that word over so it opens the next group ("to me")
      const last = cleanWord(cur[cur.length - 1].text).toLowerCase();
      if (cur.length > 1 && WEAK.has(last)) {
        const carry = cur.pop();
        flush();
        cur.push(carry);
        return;
      }
      brk = true;
    }
  }
  if (brk) flush();
});
flush();

const CAP_POS = "left:calc(540px - var(--caption-max-w) / 2);top:calc(var(--caption-y) - 70px);width:var(--caption-max-w);height:140px;z-index:40";
// Caption timing is decided in whole frames (inF shown first, outF the first frame after).
// The runtime shows a clip while start <= t < start + duration and snaps an edge to a frame
// only within 0.001 frame, so writing start and length rounded to 3 decimals separately let a
// group's end run 1 ms past the next group's start: both on screen for one frame. capSec writes a frame to 6 decimals (snaps exactly) and each length is the
// difference of the two written edges, so a group's end is the next group's start or earlier.
const toFrame = (t) => Math.round(Number(t) * FPS);
const capSec = (frame) => Math.round((frame / FPS) * 1e6) / 1e6;
const DF = toFrame(D);
const slamFrames = slamWindows.map(([s, e]) => [toFrame(s), toFrame(e)]);
let prevOutF = 0;
const caps = groups.map((g, i) => {
  const next = groups[i + 1];
  let tin = Math.max(prevOutF / FPS, g[0].start - 0.06);
  let tout = g[g.length - 1].end + (captionStyle === "bigword" ? 0.15 : 0.45);
  if (next) tout = Math.min(tout, next[0].start - 0.06);
  tout = Math.max(tout, Math.min(tin + 0.3, next ? next[0].start - 0.06 : tin + 0.3));
  let inF = toFrame(tin);
  let outF = Math.min(DF, toFrame(tout));
  // never under a word slam: groups that start before it end at the slam, groups that
  // start during it wait for the slam to finish (and vanish if they would end first)
  for (const [s, e] of slamFrames) {
    if (inF < s && outF > s) outF = s;
    else if (inF >= s && inF < e) inF = e;
  }
  prevOutF = Math.max(prevOutF, outF);
  return { text: display(g), inF, outF, tin: inF / FPS, tout: outF / FPS };
});
caps.forEach((c, i) => {
  if (!(c.tout - c.tin >= 0.1)) return;
  const id = `cap-${String(i).padStart(3, "0")}`;
  let inner;
  if (captionStyle === "bigword") {
    const size = Math.max(56, Math.min(parseFloat(tok("--bigword-size")) || 112, Math.floor((captionMaxW - 40) / Math.max(0.5, emWidth(c.text)))));
    inner = `<span class="bigword" style="font-size:${size}px">${escText(c.text)}</span>`;
  } else {
    inner = `<span class="pill">${escText(c.text)}</span>`;
  }
  const start = capSec(c.inF);
  const length = Math.round((capSec(c.outF) - start) * 1e6) / 1e6;
  layers.push(
    `<div id="${id}" class="clip cap" data-start="${start}" data-duration="${length}" data-track-index="40" style="${CAP_POS}">${inner}</div>`,
  );
  const sel = captionStyle === "bigword" ? ".bigword" : ".pill";
  const from = captionStyle === "bigword" ? 0.86 : 0.92;
  tlLines.push(`tl.fromTo("#${id} ${sel}", { scale: ${from} }, { scale: 1, duration: ${captionStyle === "bigword" ? 0.1 : 0.067}, ease: "power2.out" }, ${start});`);
  counts.captions++;
});

// ---------------------------------------------------------------- voice
layers.push(
  `<audio id="voice" src="${escAttr(recSrc)}" data-start="0" data-duration="${f3(D)}" data-media-start="${f3(recOffset)}" data-track-index="50" data-volume="1"></audio>`,
);

// ---------------------------------------------------------------- SFX cue sheet
// Only with --cues <file>. One cue per on-screen event, by cue TYPE (the audio pass maps types
// to kit files and sets levels from measured loudness). Times mirror each scene's own runtime
// logic and declared defaults, so a cue lands on the frame its event happens.
//   whoosh = drop-in / slide-in   tick = table row, step, button press, pick
//   pop = chip / check / bubble   thud = stamp, seal, word slam   keys = typing (has dur)
// Restraint: HOOK beats keep only the hook title's own cue; LOCKIN
// beats keep only thuds; accent cues (whoosh, pop) keep >= 1.0 s apart; ticks and keys keep
// >= 0.2 s from the previous kept cue; thuds always play. Per-beat shotlist overrides:
//   "sfx": false                                   mute every cue in that beat
//   "sfx": [{ "at": 12.3, "cue": "pop", "dur": 0.4 }]   add cues (recording-timeline seconds)
const cuesPath = arg("cues", "");
if (cuesPath) {
  const ev = [];
  const add = (t, cue, scene, beat, event, dur) => ev.push({ t: Math.round(t * 1000) / 1000, cue, ...(dur ? { dur: Math.round(dur * 1000) / 1000 } : {}), scene, beat, event });
  const arrOf = (x) => {
    if (Array.isArray(x)) return x;
    try {
      const a = JSON.parse(String(x || "[]"));
      return Array.isArray(a) ? a : [];
    } catch (err) {
      return [];
    }
  };
  instances.forEach((inst) => {
    const v = effectiveVars(inst.type, inst.inputs, inst.extra);
    const T = inst.start;
    const span = inst.end - inst.start;
    const at = (local) => local >= 0 && local < span;
    const A = (local, cue, what, dur) => at(local) && add(T + local, cue, inst.type, inst.beat, what, dur);
    switch (inst.type) {
      case "hook-title":
        if (String(v.visual || "")) A(0.22, "whoosh", "title visual drops");
        break;
      case "lineup":
        arrOf(v.items).slice(0, 4).forEach((it) => A(Math.max(0, Number(it.t) || 0), "whoosh", `${it.name || "item"} drops`));
        break;
      case "face-off": {
        let items = arrOf(v.items).slice(0, 3);
        if (items.length < 2) items = [{ t: 0.15 }, { t: 0.4 }];
        const ts = items.map((it, i) => (Number.isFinite(Number(it.t)) ? Math.max(0, Number(it.t)) : 0.15 + i * 0.3));
        ts.forEach((t, i) => A(t, "whoosh", `${items[i].name || `lane ${i + 1}`} drops`));
        A(Number(v.vsAt) > 0 ? Number(v.vsAt) : Math.max(...ts) + 0.45, "thud", "VS seal slams");
        if (Math.floor(Number(v.pick)) >= 0 && Number(v.pickAt) > 0) A(Number(v.pickAt), "tick", "pick lights up");
        break;
      }
      case "table":
        A(0.1, "whoosh", "card rises");
        arrOf(v.rows).slice(0, 5).forEach((r) => A(Math.max(0, Number(r.t) || 0), "tick", `row ${r.label || ""}`.trim()));
        break;
      case "stat": {
        const land = Math.max(0, Number(v.countAt) || 0) + Math.max(0.1, Number(v.countDur) || 1.1);
        A(land - 0.1, "pop", "count lands, label pops");
        break;
      }
      case "steps": {
        const steps = arrOf(v.steps).slice(0, 5);
        const times = arrOf(v.times);
        const ts = steps.map((s, i) => (Number.isFinite(Number(times[i])) && times[i] !== null ? Math.max(0, Number(times[i])) : 0.3 + i * 0.8));
        ts.forEach((t, i) => A(t, "tick", `step ${i + 1} lands`));
        if (ts.length) A(Number(v.doneAt) > 0 ? Number(v.doneAt) : ts[ts.length - 1] + 0.7, "pop", "last check lands");
        break;
      }
      case "screen-frame":
        A(Math.max(0, Number(v.enterAt) || 0), "whoosh", "frame rises");
        break;
      case "quote":
        A(0.08, "whoosh", "plate rises");
        if (v.kind === "dm") {
          String(v.text || "").split(" / ").filter((s) => s.trim() !== "").slice(0, 4).forEach((s, i) => A(0.48 + i * 0.42, "pop", `bubble ${i + 1}`));
        }
        break;
      case "receipt": {
        A(0.06, "whoosh", "card rises");
        const lines = arrOf(v.lines).slice(0, 8);
        const times = arrOf(v.times);
        const cps = Math.max(5, Math.min(120, Number(v.cps) || 40));
        let prevEnd = -1;
        const ends = [];
        lines.forEach((l, i) => {
          let text = String(l !== null && typeof l === "object" ? l.text || "" : l);
          if (text.indexOf("$ ") === 0) text = text.slice(2);
          const asked = Number.isFinite(Number(times[i])) && times[i] !== null ? Math.max(0, Number(times[i])) : 0.3 + i * 0.6;
          const t0 = Math.max(asked, prevEnd + 0.06);
          prevEnd = t0 + text.length / cps;
          ends.push(prevEnd);
          A(t0, "keys", `line ${i + 1} types`, Math.min(0.6, text.length / cps));
        });
        const hi = Math.floor(Number(v.highlight));
        if (hi >= 0 && hi < lines.length) A(Number(v.highlightAt) > 0 ? Number(v.highlightAt) : ends[hi] + 0.15, "tick", "receipt line highlights");
        break;
      }
      case "chapter":
        if (v.wipe === true || v.wipe === "true") A(0, "whoosh", "colour wipe");
        else A(0.02, "tick", "pills land");
        break;
      case "cta": {
        const keyword = String(v.keyword || "KEYWORD");
        const typeAt = Math.max(0, Number(v.typeAt) || 0.7);
        const dmAt = Math.max(typeAt + 0.4, Number(v.dmAt) || 1.8);
        const typed = keyword.length / 14;
        A(typeAt, "keys", "comment types", Math.min(0.6, typed));
        A(typeAt + typed + 0.15, "tick", "Post pressed");
        A(dmAt, "whoosh", "DM reply slides in");
        break;
      }
      default:
        break;
    }
  });
  overlayList.forEach((o) => {
    if (o.type === "stamp") add(o.start, "thud", "stamp", o.beat, "stamp slams");
    else if (o.type === "word-slam") add(o.start, "thud", "word-slam", o.beat, "word slams");
  });
  beats.forEach((b) => {
    if (b.fallbackFrame) add(b.start + 0.05, "whoosh", "screen-frame", b.id, "proof card rises");
    if (Array.isArray(b.sfx)) {
      b.sfx.forEach((c) => {
        if (c && ["whoosh", "tick", "pop", "thud", "keys"].includes(c.cue) && Number.isFinite(Number(c.at))) add(Number(c.at), c.cue, "manual", b.id, "shotlist sfx", Number(c.dur) || 0);
        else warn(`beat ${b.id}: sfx entries need {at, cue: whoosh|tick|pop|thud|keys}`);
      });
    }
  });

  // restraint pass
  const beatAt = (t) => beats.find((b) => t >= b.start - 1e-6 && t < b.end - 1e-6) || beats[beats.length - 1];
  const kept = [];
  const dropped = [];
  let lastAccent = -99;
  let lastAny = -99;
  ev.sort((a, b) => a.t - b.t || (a.cue === "thud" ? -1 : 1));
  ev.forEach((c) => {
    const b = beatAt(c.t);
    const tag = String(b.tag || "").toUpperCase();
    let reason = "";
    if (c.t < 0 || c.t >= D) reason = "outside the video";
    else if (b.sfx === false) reason = `beat ${b.id} has "sfx": false`;
    else if (b.ownAudio === true) reason = `beat ${b.id} plays its own audio ("ownAudio": true)`;
    else if (c.scene !== "manual" && tag === "HOOK" && c.scene !== "hook-title") reason = "HOOK beat: only the hook title's cue plays";
    else if (c.scene !== "manual" && tag === "LOCKIN" && c.cue !== "thud") reason = "LOCKIN beat: only thuds play";
    else if (c.scene !== "manual" && (c.cue === "whoosh" || c.cue === "pop") && c.t - lastAccent < 1.0) reason = "accent cue within 1.0 s of the previous one";
    else if (c.scene !== "manual" && (c.cue === "tick" || c.cue === "keys") && c.t - lastAny < 0.2) reason = "within 0.2 s of the previous cue";
    if (reason) {
      dropped.push({ ...c, reason });
      return;
    }
    kept.push(c);
    lastAny = c.t;
    if (c.cue !== "tick" && c.cue !== "keys") lastAccent = c.t;
  });
  // end of the first run of HOOK beats (kept in the sheet; the bed itself starts at 0:00)
  let hookEnd = 0;
  for (const b of beats) {
    if (String(b.tag || "").toUpperCase() === "HOOK") hookEnd = b.end;
    else break;
  }
  // beats marked "ownAudio": true carry footage whose own sound is cut into the recording's audio
  // (e.g. a finished clip). The audio pass keeps that span out of the voice chain, levels it on
  // its own and dips the bed under it. Sheets without such beats are unchanged.
  const ownAudio = [];
  beats.forEach((b) => {
    if (b.ownAudio !== true) return;
    const last = ownAudio[ownAudio.length - 1];
    if (last && Math.abs(last.end - b.start) < 1e-6) {
      last.end = b.end;
      last.beats.push(b.id);
    } else ownAudio.push({ start: b.start, end: b.end, beats: [b.id] });
  });
  const sheet = { version: 1, about: "SFX cue sheet written by scripts/build.mjs --cues; read by scripts/audio-pass.mjs", duration: D, hookEnd, ...(ownAudio.length ? { ownAudio } : {}), cues: kept, dropped };
  try {
    mkdirSync(dirname(resolve(ROOT, cuesPath)), { recursive: true });
    writeFileSync(resolve(ROOT, cuesPath), JSON.stringify(sheet, null, 2) + "\n");
  } catch (err) {
    fail(`cannot write the cue sheet ${cuesPath}: ${err.message}`);
  }
  console.log(`[build] sfx cues: ${kept.length} kept, ${dropped.length} dropped by the restraint rules -> ${cuesPath}`);
}

// ---------------------------------------------------------------- write
const html = shell
  .replace("@@DURATION@@", f3(D))
  .replace("<!-- @@LAYERS@@ -->", layers.join("\n      "))
  .replace("/* @@TIMELINE@@ */", tlLines.join("\n      "));
writeFileSync(outPath, html);

const modeTime = {};
beats.forEach((b) => (modeTime[b.eff] = (modeTime[b.eff] || 0) + (b.end - b.start)));
console.log(`[build] brand: ${variant.name || variantPath}  (${variantPath})`);
console.log(`[build] tokens: caption-style=${captionStyle} max-words=${maxWords} proof-split=${proofSplit ? "on" : "off"} grade=${gradeIntensity} accent=${tok("--accent")}`);
const proofBeats = beats.filter((b) => b.proof && ["A", "A2"].includes(b.mode));
if (proofBeats.length) {
  console.log(`[build] real-footage layout: ` + proofBeats.map((b) => `${b.id} ${b.eff === "A2" ? "split" : "card"} (${b.layout ? "shot list" : "token"})`).join(", "));
}
console.log(`[build] ${beats.length} beats, ${f3(D)}s: ` + Object.entries(modeTime).map(([m, t]) => `${m} ${f3(t)}s (${Math.round((t / D) * 100)}%)`).join(", "));
console.log(`[build] ${counts.scenes} scene hosts, ${counts.faces} face clips, ${counts.plates} footage plates, ${counts.overlays} overlays, ${counts.captions} captions`);
if (freeNotes.length) console.log(`[build] free face (no box): ${freeNotes.join("; ")}`);
console.log(`[build] wrote ${outPath}`);
