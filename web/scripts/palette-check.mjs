// Measures the palette in src/styles/tokens.css: contrast (WCAG), distinctness (CIE76 delta E) and chroma budgets.
// Zero dependencies. Exit 1 if any requirement fails or a planted control is not detected.
//
// Metric choice (references/instrument-traps.md): contrast ratio answers "can this text be read on that ground";
// delta E answers "are these two colours different". Each question gets its own instrument.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "..", "src", "styles", "tokens.css"), "utf8");

// ---- colour maths ----------------------------------------------------------------------------------------------
const clamp01 = (v) => Math.min(1, Math.max(0, v));
function oklchToLinear(L, C, H) {
  const h = (H * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}
const inGamut = (lin) => lin.every((v) => v >= -0.0005 && v <= 1.0005);
const luminance = ([r, g, b]) => 0.2126 * clamp01(r) + 0.7152 * clamp01(g) + 0.0722 * clamp01(b);
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
function toLab(lin) {
  const [r, g, b] = lin.map(clamp01);
  const X = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b;
  const Y = 0.2126729 * r + 0.7151522 * g + 0.072175 * b;
  const Z = 0.0193339 * r + 0.119192 * g + 0.9503041 * b;
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : ((24389 / 27) * t + 16) / 116);
  const [fx, fy, fz] = [f(X / 0.95047), f(Y), f(Z / 1.08883)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
const deltaE = (a, b) => Math.hypot(...toLab(a).map((v, i) => v - toLab(b)[i]));

// ---- parse the three token blocks -------------------------------------------------------------------------------
function block(re) {
  const m = css.match(re);
  if (!m) throw new Error(`token block not found: ${re}`);
  return m[1];
}
function tokens(text) {
  const out = {};
  for (const m of text.matchAll(/--([a-z-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)/g)) {
    out[m[1]] = [Number(m[2]), Number(m[3]), Number(m[4])];
  }
  return out;
}
const themes = {
  light: tokens(block(/:root,\s*:root\[data-theme="light"\]\s*\{([\s\S]*?)\n\}/)),
  darkSystem: tokens(block(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{([\s\S]*?)\n  \}/)),
  darkSwitch: tokens(block(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)),
};

let failures = 0;
const fail = (msg) => {
  failures++;
  console.log("  FAIL", msg);
};

// ---- planted controls: the instruments must be able to fail ------------------------------------------------------
{
  const white = oklchToLinear(1, 0, 0);
  const near = oklchToLinear(0.97, 0, 0);
  const black = oklchToLinear(0, 0, 0);
  if (!(contrast(white, near) < 1.1)) fail("control: near-identical colours must read below 1.1:1");
  if (!(contrast(white, black) > 20)) fail("control: black on white must read above 20:1");
  const red = oklchToLinear(0.6, 0.2, 29);
  const green = oklchToLinear(0.6, 0.2, 145);
  if (!(deltaE(red, green) > 60)) fail("control: red and green must be far apart in delta E");
  if (!(inGamut(oklchToLinear(0.7, 0.1, 170)) && !inGamut(oklchToLinear(0.7, 0.4, 170)))) fail("control: gamut test");
  if (failures) {
    console.log("palette-check: a planted control failed, results withheld");
    process.exit(2);
  }
}

// ---- requirements --------------------------------------------------------------------------------------------------
const TEXT = [
  ["ink", "ground"], ["ink", "surface"], ["ink", "sunk"], ["ink-muted", "ground"], ["ink-muted", "surface"],
  ["ink-muted", "sunk"], ["on-accent", "accent"], ["accent-ink", "ground"], ["accent-ink", "surface"],
  ["accent-ink", "accent-wash"], ["ink", "accent-wash"], ["source", "ground"], ["source", "surface"],
  ["source", "source-wash"], ["terrain-ink", "ground"], ["terrain-ink", "surface"], ["reject", "ground"],
  ["reject", "surface"], ["reject", "reject-wash"], ["ink", "reject-wash"],
];
const NONTEXT = [["line-strong", "ground"], ["accent", "ground"], ["accent", "surface"], ["source", "ground"], ["reject", "ground"]];
const HUES = ["accent", "source", "terrain", "reject"];
const SURFACES = ["ground", "surface", "sunk"];

for (const [name, t] of Object.entries(themes)) {
  console.log(`\n${name}`);
  const lin = Object.fromEntries(Object.entries(t).map(([k, v]) => [k, oklchToLinear(...v)]));
  for (const [k, v] of Object.entries(lin)) if (!inGamut(v)) fail(`${k} is outside sRGB`);
  for (const [fg, bg] of TEXT) {
    const r = contrast(lin[fg], lin[bg]);
    console.log(`  text   ${fg.padEnd(11)} on ${bg.padEnd(12)} ${r.toFixed(2)}:1`);
    if (r < 4.5) fail(`${fg} on ${bg} is ${r.toFixed(2)}:1, needs 4.5`);
  }
  for (const [fg, bg] of NONTEXT) {
    const r = contrast(lin[fg], lin[bg]);
    console.log(`  shape  ${fg.padEnd(11)} on ${bg.padEnd(12)} ${r.toFixed(2)}:1`);
    if (r < 3) fail(`${fg} on ${bg} is ${r.toFixed(2)}:1, needs 3`);
  }
  for (let i = 0; i < HUES.length; i++) {
    for (let j = i + 1; j < HUES.length; j++) {
      const d = deltaE(lin[HUES[i]], lin[HUES[j]]);
      console.log(`  deltaE ${HUES[i].padEnd(8)} vs ${HUES[j].padEnd(8)} ${d.toFixed(1)}`);
      if (d < 20) fail(`${HUES[i]} and ${HUES[j]} are only deltaE ${d.toFixed(1)} apart, need 20`);
    }
  }
  const surfaceC = Math.max(...SURFACES.map((s) => t[s][1]));
  const ratio = t.accent[1] / surfaceC;
  console.log(`  chroma accent ${t.accent[1]} vs max surface ${surfaceC}  (x${ratio.toFixed(1)})`);
  if (ratio < 4) fail(`accent chroma is only x${ratio.toFixed(1)} the surface chroma, need 4`);
  for (const s of SURFACES) if (t[s][1] < 0.004 || t[s][1] > 0.03) fail(`${s} chroma ${t[s][1]} is outside 0.004-0.03`);
}

// the two dark blocks must be the same palette
for (const k of Object.keys(themes.darkSystem)) {
  if (JSON.stringify(themes.darkSystem[k]) !== JSON.stringify(themes.darkSwitch[k])) fail(`dark blocks differ at --${k}`);
}
if (Object.keys(themes.darkSystem).length !== Object.keys(themes.darkSwitch).length) fail("dark blocks have different token sets");
for (const k of Object.keys(themes.light)) if (!(k in themes.darkSwitch)) fail(`--${k} has no dark value`);

console.log(failures ? `\npalette-check: ${failures} failure(s)` : "\npalette-check: all requirements hold");
process.exit(failures ? 1 : 0);
