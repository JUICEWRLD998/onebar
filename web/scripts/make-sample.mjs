// Fetch real elevation grids for the recorded examples and turn them into contour paths with the same library the
// browser uses. Run once; the output is committed so the recorded examples work offline.
//   node scripts/make-sample.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { fetchContours } from "../src/lib/terrain.ts";

const here = dirname(fileURLToPath(import.meta.url));
const examples = JSON.parse(readFileSync(join(here, "..", "src", "data", "examples.json"), "utf8"));

const out = {};
for (const e of examples) {
  const { lat, lon } = e.place;
  const c = await fetchContours(lat, lon);
  out[e.id] = { lat, lon, contours: c };
  console.log(e.id, e.place.name, `${c.min}-${c.max} m`, `${c.levels.length} levels every ${c.interval} m`,
    `minor ${(c.minor.length / 1024).toFixed(1)} KB major ${(c.major.length / 1024).toFixed(1)} KB`);
  await new Promise((r) => setTimeout(r, 800)); // be polite to the free API
}
writeFileSync(join(here, "..", "src", "data", "terrain.json"), JSON.stringify(out) + "\n");
console.log("wrote src/data/terrain.json");
