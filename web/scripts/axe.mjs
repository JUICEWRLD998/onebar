// Runs axe-core (from node_modules) against each route in a real browser, in light and dark.
//   node scripts/axe.mjs --url http://localhost:4183
// States: the Ask page as first seen, the Ask page after replaying a recorded example (the audit sheet and the leader
// line), the base-model view, Results, How it works and a trace page. Exit code 1 if any serious or critical violation.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { launch, sleep } from "./lib/cdp.mjs";

const args = process.argv.slice(2);
const base = args[args.indexOf("--url") + 1] ?? "http://localhost:4183";
const axeSource = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "node_modules", "axe-core", "axe.min.js"), "utf8");

const run = (page) =>
  page.evaluate(`(async () => {
    const r = await axe.run(document, { resultTypes: ['violations'] });
    return JSON.stringify(r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\\n').slice(1, 3).join(' ')) })));
  })()`);

const states = [
  { name: "ask-first", path: "/", steps: [] },
  { name: "ask-replayed", path: "/", steps: ["ridge ok by 3:30pm then car?"] },
  { name: "ask-base", path: "/", steps: ["ridge ok by 3:30pm then car?", "Base model"] },
  { name: "results", path: "/results", steps: [] },
  { name: "how", path: "/how-it-works", steps: [] },
  { name: "trace", path: "/trace/example-ridge", steps: [] },
];

let bad = 0;
const chrome = await launch({ port: 9466 });
try {
  const page = await chrome.newPage();
  for (const scheme of ["light", "dark"]) {
    await page.emulate({ width: 1280, height: 900, scheme });
    for (const s of states) {
      await page.goto(`${base}${s.path}?theme=${scheme}`);
      for (const text of s.steps) {
        await page.clickText(text);
        await sleep(1700);
      }
      await page.evaluate(axeSource);
      const v = JSON.parse(await run(page));
      const serious = v.filter((x) => x.impact === "serious" || x.impact === "critical");
      bad += serious.length;
      console.log(`${scheme.padEnd(5)} ${s.name.padEnd(13)} violations ${v.length} (serious+critical ${serious.length})`);
      for (const x of v) console.log(`   ${x.impact} ${x.id}: ${x.help}\n     ${x.nodes.join("\n     ")}`);
    }
  }
  await page.close();
} finally {
  await chrome.close();
}
process.exit(bad ? 1 : 0);
