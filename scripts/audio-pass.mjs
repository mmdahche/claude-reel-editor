#!/usr/bin/env node
// Audio pass: voice chain + SFX on the beats + optional ducked music bed -> a pre-master mix
// that render.sh then masters (one fixed gain to -14.5 LUFS, oversampled peak limiter, true peak
// target -1.5 dBTP) under the picture.
//
// usage: node scripts/audio-pass.mjs --body <render.mp4> --cues <sfx-cues.json> --out <dir>
//          [--music <file>] [--bed-lufs -19] [--voice-lufs -16] [--master-lufs -14.5] [--voice-eq on|off]
//   --body    the HyperFrames body render (its audio IS the voice, already on the timeline). Clean
//             the raw voice with DeepFilterNet BEFORE the build (scripts/clean-voice.sh), so the
//             recording the build uses already carries the cleaned voice.
//   --cues    cue sheet from `node scripts/build.mjs --cues <file>`
//   --music   optional bed: ducked under speech with sidechain compression, starts at 0:00 with a
//             0.5 s fade-in (a cue sheet "bedStart" overrides it), fades out over the last 1.5 s.
//             Without it the mix has no music. Every bed needs a licence row (assets/music/README.md).
//   --voice-eq on (default): highpass 80 Hz, -3 dB at 300 Hz, +6 dB at 3.2 kHz, high shelf +4 dB
//             at 6.5 kHz (lifts a muffled small-room recording), then level and limiter.
//             off: highpass 80 Hz, level and limiter only. Never a compressor or de-esser.
// writes <out>/voice-clean.wav  the voice chain above, levelled to --voice-lufs integrated
//        <out>/sfx.wav          SFX bus (each cue trimmed, faded, level-set from its measured
//                               max momentary loudness so it lands 6-10 dB under the voice)
//        <out>/music-bed.wav    (--music only) the ducked bed
//        <out>/mix.wav          voice + SFX (+ bed), bus limiter at -4 dBFS (pre-master)
//        <out>/mix-nomusic.wav  voice + SFX (always written, so there are always two exports)
//        <out>/sfx-cues.json    resolved cues: kit file, start, length, gain
//        <out>/report.json      measured levels
// Own-audio windows (cue sheet "ownAudio", from shot-list beats with "ownAudio": true): that span
// of the body audio is finished footage, not voice. It is muted out of the voice chain, levelled
// on its own to --own-lufs (default: the voice target) into <out>/own-audio.wav, mixed in, and
// the music bed dips --own-dip dB (default -14) under it with 0.25 s ramps.
// Levels: SFX targets are FINAL momentary loudness (after mastering); the pass subtracts the
// expected master gain (master - voice) so they land there.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

// Cue type -> kit file. The kit ships NO sound files (their licences forbid redistributing them):
// put your own licensed files at assets/sfx/<cue>.wav|.mp3|.m4a (see assets/sfx/README.md).
// A cue type with no file is skipped with a warning, so the pipeline still runs.
//   in    seconds skipped at the file start      max   longest piece used (<= 0.6 s)
//   pre   the file starts this early, so its transient lands on the event
//   fade  fade-out length                        target final max momentary loudness (LUFS)
// Optional per-file trim: assets/sfx/<cue>.json {"in": 0.4} (e.g. a typing file with a slow start).
const KIT = {
  whoosh: { in: 0, max: 0.57, pre: 0.04, fade: 0.15, target: -22 },
  tick: { in: 0, max: 0.36, pre: 0.05, fade: 0.08, target: -24 },
  pop: { in: 0, max: 0.6, pre: 0.1, fade: 0.2, target: -23 },
  thud: { in: 0, max: 0.6, pre: 0.03, fade: 0.3, target: -21 },
  keys: { in: 0, max: 0.6, pre: 0, fade: 0.08, target: -24 },
};
for (const [cue, k] of Object.entries(KIT)) {
  const found = ["wav", "mp3", "m4a", "aiff", "ogg"].map((ext) => `assets/sfx/${cue}.${ext}`).find((f) => existsSync(join(ROOT, f)));
  k.file = found || "";
  const trim = join(ROOT, "assets", "sfx", `${cue}.json`);
  if (found && existsSync(trim)) {
    try {
      const t = JSON.parse(readFileSync(trim, "utf8"));
      if (Number.isFinite(Number(t.in)) && Number(t.in) >= 0) k.in = Number(t.in);
    } catch (err) {
      console.error(`[audio-pass] warning: ignoring ${trim}: ${err.message}`);
    }
  }
}
const SR = 48000;
const FMT = `aformat=sample_rates=${SR}:sample_fmts=fltp:channel_layouts=stereo`;

// ---------------------------------------------------------------- utils
function fail(msg) {
  console.error(`[audio-pass] ERROR: ${msg}`);
  process.exit(1);
}
function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  if (i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--")) return process.argv[i + 1];
  return fallback;
}
function ff(args, what) {
  const res = spawnSync("ffmpeg", ["-hide_banner", "-nostats", ...args], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (res.error) fail(`${what}: ${res.error.message}`);
  if (res.status !== 0) fail(`${what}: ffmpeg exited ${res.status}\n${(res.stderr || "").split("\n").slice(-8).join("\n")}`);
  return res.stderr || "";
}
// integrated loudness, max momentary and true peak of a filter graph's output
function measure(inputArgs, chain, what) {
  const log = ff([...inputArgs, "-vn", "-af", `${chain ? chain + "," : ""}ebur128=peak=true`, "-f", "null", "-"], what);
  const ms = [...log.matchAll(/ M:\s*(-?[0-9.]+) S:/g)].map((m) => Number(m[1]));
  const sum = log.slice(log.lastIndexOf("Summary:"));
  const I = Number((sum.match(/I:\s*(-?[0-9.]+) LUFS/) || [])[1]);
  const TP = Number((sum.match(/Peak:\s*(-?[0-9.inf]+) dBFS/) || [])[1]);
  return { I, maxM: ms.length ? Math.max(...ms) : -120, TP };
}
const r1 = (n) => Math.round(n * 10) / 10;
const r3 = (n) => Math.round(n * 1000) / 1000;

// ---------------------------------------------------------------- inputs
const body = resolve(arg("body", ""));
const cuesPath = resolve(arg("cues", ""));
const outDir = resolve(arg("out", ""));
const music = arg("music", "") ? resolve(arg("music", "")) : "";
const voiceLufs = Number(arg("voice-lufs", -16));
const masterLufs = Number(arg("master-lufs", -14.5));
const bedLufs = Number(arg("bed-lufs", -19)); // music bed level (final) in the gaps; ducked under speech it sits ~7-8 dB lower
const voiceEq = arg("voice-eq", "on") !== "off";
if (!arg("body", "") || !existsSync(body)) fail(`--body not found: ${body}`);
if (!arg("cues", "") || !existsSync(cuesPath)) fail(`--cues not found: ${cuesPath}`);
if (!arg("out", "")) fail("--out <dir> is required");
if (music && !existsSync(music)) fail(`--music not found: ${music}`);
if (!Number.isFinite(voiceLufs) || !Number.isFinite(masterLufs)) fail("--voice-lufs / --master-lufs must be numbers");
let sheet;
try {
  sheet = JSON.parse(readFileSync(cuesPath, "utf8"));
} catch (err) {
  fail(`cannot read the cue sheet: ${err.message}`);
}
const D = Number(sheet.duration);
if (!(D > 0)) fail("cue sheet has no duration");
// the bed starts at 0:00, under the hook (a late bed made the opening feel empty); a sheet
// "bedStart" may override it
const bedStart = Math.max(0, Math.min(D - 2, Number.isFinite(Number(sheet.bedStart)) ? Number(sheet.bedStart) : 0));
mkdirSync(outDir, { recursive: true });
const masterGain = masterLufs - voiceLufs; // what mastering will add to everything

// own-audio windows (see the header); none -> every chain below is exactly what it was before
const own = (Array.isArray(sheet.ownAudio) ? sheet.ownAudio : [])
  .map((w) => ({ start: Number(w.start), end: Number(w.end), beats: w.beats || [] }))
  .filter((w) => Number.isFinite(w.start) && Number.isFinite(w.end) && w.end > w.start && w.start < D)
  .map((w) => ({ ...w, end: Math.min(D, w.end) }));
const ownLufs = Number(arg("own-lufs", voiceLufs));
const ownDip = Number(arg("own-dip", -14));
if (!Number.isFinite(ownLufs) || !Number.isFinite(ownDip) || ownDip > 0) fail("--own-lufs must be a number and --own-dip a number <= 0");
// per-sample gate (aeval runs sample by sample, so the switch lands exactly on the cut)
const inOwn = own.map((w) => `between(t,${r3(w.start)},${r3(w.end)})`).join("+");
const VMASK = own.length ? `,aeval=exprs='val(0)*(1-(${inOwn}))|val(1)*(1-(${inOwn}))':c=same` : "";
const OMASK = own.length ? `,aeval=exprs='val(0)*(${inOwn})|val(1)*(${inOwn})':c=same` : "";

// ---------------------------------------------------------------- 1. voice chain
const raw = measure(["-i", body], `${FMT}${VMASK}`, "measure the raw voice");
if (!Number.isFinite(raw.I) || raw.I < -60) fail(`the body render has no usable voice (integrated ${raw.I} LUFS)`);
// voice: the raw take was already cleaned by DeepFilterNet before the build. Here: highpass, the
// optional presence EQ, level, limiter. No compressor, no de-esser, no extra denoise (a broadband
// denoise added static and a compressor + de-esser sounded muffled in listening tests). None of
// these filters adds latency, so the voice stays sample-aligned with the picture.
const EQ = ",equalizer=f=300:t=o:w=1.2:g=-3,equalizer=f=3200:t=o:w=2:g=6,highshelf=f=6500:g=4";
const chain = `${FMT}${VMASK},highpass=f=80:poles=2${voiceEq ? EQ : ""}`;
const postM = measure(["-i", body], chain, "measure the highpassed voice");
const voiceOut = join(outDir, "voice-clean.wav");
// level to the voice target first, then the limiter (-1 dBFS) so the stem never clips
const voiceChain = `${chain},volume=${r3(voiceLufs - postM.I)}dB,alimiter=limit=0.891:attack=5:release=60:level=false:latency=1`;
ff(["-y", "-i", body, "-vn", "-af", `${voiceChain},atrim=duration=${D},asetpts=PTS-STARTPTS`, "-c:a", "pcm_s24le", voiceOut], "write voice-clean.wav");
const voice = measure(["-i", voiceOut], "", "measure voice-clean.wav");
console.log(`[audio-pass] voice: raw ${r1(raw.I)} LUFS -> highpass 80 Hz${voiceEq ? " + presence EQ" : ""} + level -> ${r1(voice.I)} LUFS, true peak ${r1(voice.TP)} dBTP (limiter -1 dBFS)`);

// ---------------------------------------------------------------- 1b. own audio (windows only)
let ownStem = null;
if (own.length) {
  const ownRaw = measure(["-i", body], `${FMT}${OMASK}`, "measure the own-audio windows");
  if (!Number.isFinite(ownRaw.I) || ownRaw.I < -60) fail(`the own-audio windows are silent (integrated ${ownRaw.I} LUFS)`);
  const ownGain = r3(ownLufs - ownRaw.I);
  const ownOut = join(outDir, "own-audio.wav");
  ff(["-y", "-i", body, "-vn", "-af", `${FMT}${OMASK},volume=${ownGain}dB,alimiter=limit=0.891:attack=5:release=60:level=false:latency=1,atrim=duration=${D},asetpts=PTS-STARTPTS`, "-c:a", "pcm_s24le", ownOut], "write own-audio.wav");
  const ownM = measure(["-i", ownOut], "", "measure own-audio.wav");
  ownStem = { file: ownOut, windows: own, sourceI: r1(ownRaw.I), gainDb: ownGain, targetI: ownLufs, I: r1(ownM.I), TP: r1(ownM.TP), chain: "levelled only (no highpass, compressor or de-esser), alimiter -1 dBFS" };
  console.log(`[audio-pass] own audio: ${own.map((w) => `${r3(w.start)}-${r3(w.end)} s`).join(", ")} kept out of the voice chain; ${r1(ownRaw.I)} LUFS -> ${r1(ownM.I)} LUFS, true peak ${r1(ownM.TP)} dBTP`);
}

// ---------------------------------------------------------------- 2. SFX bus
const gainCache = new Map();
const missingCues = new Set();
const resolved = [];
for (const c of sheet.cues || []) {
  const k = KIT[c.cue];
  if (!k) {
    console.error(`[audio-pass] warning: no kit sound for cue type "${c.cue}" at ${c.t}s (skipped)`);
    continue;
  }
  if (!k.file) {
    missingCues.add(c.cue);
    continue;
  }
  const kitFile = join(ROOT, k.file);
  const len = r3(c.cue === "keys" && c.dur ? Math.min(k.max, Math.max(0.15, c.dur + 0.08)) : k.max);
  const fade = Math.min(k.fade, len / 2);
  const shape = `${FMT},afade=t=out:st=${r3(len - fade)}:d=${r3(fade)}`;
  const key = `${c.cue}|${len}`;
  if (!gainCache.has(key)) {
    const m = measure(["-ss", String(k.in), "-t", String(len), "-i", kitFile], `${shape},apad=pad_dur=0.5`, `measure ${k.file}`);
    gainCache.set(key, { maxM: m.maxM, gain: r1(k.target - masterGain - m.maxM) });
  }
  const g = gainCache.get(key);
  const start = Math.max(0, c.t - k.pre);
  resolved.push({ ...c, file: k.file, in: k.in, start: r3(start), len, fade: r3(fade), shape, gainDb: g.gain, measuredMaxM: r1(g.maxM), finalTargetM: k.target });
}
if (missingCues.size) console.error(`[audio-pass] warning: no sound file for cue type(s) ${[...missingCues].join(", ")}: those cues were skipped. Add licensed files to assets/sfx/ (see assets/sfx/README.md).`);
const sfxOut = join(outDir, "sfx.wav");
if (resolved.length) {
  const inputs = [];
  const parts = [];
  resolved.forEach((c, i) => {
    inputs.push("-ss", String(c.in), "-t", String(c.len), "-i", join(ROOT, c.file));
    const ms = Math.round(c.start * 1000);
    parts.push(`[${i}:a]${c.shape},volume=${c.gainDb}dB,adelay=delays=${ms}:all=1[c${i}]`);
  });
  const mixIn = resolved.map((c, i) => `[c${i}]`).join("");
  parts.push(`${mixIn}amix=inputs=${resolved.length}:normalize=0:duration=longest,apad,atrim=duration=${D},asetpts=PTS-STARTPTS[sfx]`);
  ff(["-y", ...inputs, "-filter_complex", parts.join(";"), "-map", "[sfx]", "-c:a", "pcm_s24le", sfxOut], "write sfx.wav");
} else {
  ff(["-y", "-f", "lavfi", "-t", String(D), "-i", `anullsrc=r=${SR}:cl=stereo`, "-c:a", "pcm_s24le", sfxOut], "write a silent sfx.wav");
}
const sfx = resolved.length ? measure(["-i", sfxOut], "", "measure sfx.wav") : { maxM: -120, TP: -120 };
console.log(`[audio-pass] sfx: ${resolved.length} cues; bus max momentary ${r1(sfx.maxM)} LUFS pre-master (~${r1(sfx.maxM + masterGain)} after mastering)`);

// ---------------------------------------------------------------- 3. music bed (optional)
let bed = null;
if (music) {
  const mus = measure(["-t", "90", "-i", music], FMT, "measure the music");
  if (!Number.isFinite(mus.I) || mus.I < -60) fail(`--music is silent or unreadable (${mus.I} LUFS)`);
  // bed sits at --bed-lufs (default -19 LUFS, final) in the gaps; the voice key ducks it ~7-8 dB under speech
  const gain = r3(bedLufs - masterGain - mus.I);
  const span = D - bedStart;
  const bedOut = join(outDir, "music-bed.wav");
  // own-audio windows: the bed also dips ownDip dB under them, ramping over RAMP s either side
  const RAMP = 0.25;
  const dipW = own.map((w) => `clip(min((t-${r3(w.start - RAMP)})/${RAMP},(${r3(w.end + RAMP)}-t)/${RAMP}),0,1)`).join("+");
  const DIP = own.length ? `;[bd]volume='pow(10,${ownDip}*min(1,${dipW})/20)':eval=frame[bed]` : "";
  const graph = [
    `[0:a]${FMT},atrim=duration=${r3(span)},asetpts=PTS-STARTPTS,volume=${gain}dB,afade=t=in:d=0.5,afade=t=out:st=${r3(Math.max(0, span - 1.5))}:d=1.5,adelay=delays=${Math.round(bedStart * 1000)}:all=1,apad,atrim=duration=${D}[m]`,
    `[1:a]${FMT}[key]`,
    `[m][key]sidechaincompress=threshold=0.063:ratio=3:attack=15:release=400:knee=4:makeup=1${own.length ? "[bd]" : "[bed]"}${DIP}`,
  ].join(";");
  ff(["-y", "-stream_loop", "-1", "-i", music, "-i", voiceOut, "-filter_complex", graph, "-map", "[bed]", "-t", String(D), "-c:a", "pcm_s24le", bedOut], "write music-bed.wav");
  const free = measure(["-i", bedOut], `atrim=start=${r3(bedStart)}`, "measure the bed");
  bed = { file: bedOut, source: music, gainDb: gain, sourceI: r1(mus.I), bedI: r1(free.I), startsAt: r3(bedStart) };
  if (own.length) {
    // how far under the own audio the bed actually sits (both pre-master)
    const under = own.map((w) => {
      const seg = `atrim=start=${r3(w.start)}:end=${r3(w.end)}`;
      const b = measure(["-i", bedOut], seg, "measure the bed under the own audio");
      const o = measure(["-i", ownStem.file], seg, "measure the own audio window");
      return { start: r3(w.start), end: r3(w.end), bedI: r1(b.I), ownI: r1(o.I), bedUnderOwnDb: r1(o.I - b.I) };
    });
    bed.ownAudioDip = { dipDb: ownDip, rampS: RAMP, windows: under };
    console.log(`[audio-pass] music: dips ${ownDip} dB under the own audio (${under.map((u) => `${u.start}-${u.end} s: bed ${u.bedI} LUFS, ${u.bedUnderOwnDb} dB under`).join("; ")})`);
  }
  console.log(`[audio-pass] music: ${music} at ${gain} dB, ducked under the voice; bed ${r1(free.I)} LUFS pre-master from ${r3(bedStart)} s`);
}

// ---------------------------------------------------------------- 4. mix (+ no-music mix)
function mix(stems, out) {
  const ins = stems.flatMap((s) => ["-i", s]);
  const labels = stems.map((s, i) => `[${i}:a]`).join("");
  ff(["-y", ...ins, "-filter_complex", `${labels}amix=inputs=${stems.length}:normalize=0:duration=first,alimiter=limit=0.631:attack=5:release=80:level=false:latency=1[a]`, "-map", "[a]", "-c:a", "pcm_s24le", out], `write ${out}`);
  return measure(["-i", out], "", `measure ${out}`);
}
const mixOut = join(outDir, "mix.wav");
const base = ownStem ? [voiceOut, sfxOut, ownStem.file] : [voiceOut, sfxOut];
const mixM = mix(bed ? [...base, bed.file] : base, mixOut);
// the no-music mix is always written: two exports every time (with no bed they are the same audio)
const noMusicM = mix(base, join(outDir, "mix-nomusic.wav"));
console.log(`[audio-pass] mix: ${r1(mixM.I)} LUFS, true peak ${r1(mixM.TP)} dBTP (pre-master) -> ${mixOut}`);

// ---------------------------------------------------------------- 5. logs
const sfxLog = resolved.map(({ shape, ...c }) => c);
writeFileSync(join(outDir, "sfx-cues.json"), JSON.stringify({ duration: D, cues: sfxLog, dropped: sheet.dropped || [] }, null, 2) + "\n");
const report = {
  voice: { rawI: r1(raw.I), I: r1(voice.I), TP: r1(voice.TP), chain: `highpass 80 Hz${voiceEq ? ", EQ -3 dB @300 Hz, +6 dB @3.2 kHz, high shelf +4 dB @6.5 kHz" : ""}, level to ${voiceLufs} LUFS, alimiter -1 dBFS (no compressor or de-esser)` },
  sfx: { cues: resolved.length, busMaxM: r1(sfx.maxM), expectedFinalMaxM: r1(sfx.maxM + masterGain), masterGainAssumed: masterGain },
  ...(ownStem ? { ownAudio: ownStem } : {}),
  music: bed,
  mix: { I: r1(mixM.I), TP: r1(mixM.TP), file: mixOut },
  mixNoMusic: { I: r1(noMusicM.I), TP: r1(noMusicM.TP), file: join(outDir, "mix-nomusic.wav") },
};
writeFileSync(join(outDir, "report.json"), JSON.stringify(report, null, 2) + "\n");
console.log(`[audio-pass] wrote ${outDir}/{voice-clean,sfx,${ownStem ? "own-audio," : ""}mix,mix-nomusic${bed ? ",music-bed" : ""}}.wav + sfx-cues.json + report.json`);
