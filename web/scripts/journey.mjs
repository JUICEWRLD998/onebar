// Drives the primary journey in a real browser and saves a filmstrip of the signature moment.
//   node scripts/journey.mjs --url http://localhost:4183 --out <dir> [--width 1280] [--scheme light] [--reduced]
// Journey: open Ask, replay a recorded example, watch the audit play, hover a number, toggle the base model.
import { launch, sleep } from "./lib/cdp.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i === -1 ? d : args[i + 1];
};
const url = opt("url", "http://localhost:4183");
const out = opt("out", "shots");
const width = Number(opt("width", "1280"));
const scheme = opt("scheme", "light");
const reduced = args.includes("--reduced");
const tag = `${scheme}-${width}${reduced ? "-reduced" : ""}`;

const chrome = await launch({ port: 9455 });
try {
  const page = await chrome.newPage();
  await page.emulate({ width, height: width < 500 ? 812 : 900, scheme, reducedMotion: reduced });
  await page.goto(url);

  const clicked = await page.clickText("ridge ok by 3:30pm then car?");
  console.log("clicked recorded example:", clicked);
  // The thread appears; the reply lands after a 650 ms pause, then the audit plays for about a second.
  const frames = [500, 700, 850, 1000, 1150, 1300, 1500, 2200];
  let last = 0;
  for (const t of frames) {
    await sleep(t - last);
    last = t;
    await page.screenshot(`${out}/film-${tag}-${String(t).padStart(4, "0")}.jpg`, { format: "jpeg", quality: 70 });
  }
  const state = await page.evaluate(`(() => ({
    verdict: document.querySelector('[class*="verdict"]')?.textContent,
    tokens: [...document.querySelectorAll('button[class*="token"]')].map(b => b.textContent + ':' + b.dataset.state),
    leader: !!document.querySelector('svg[class*="overlay"]'),
    checks: [...document.querySelectorAll('[class*="check"][data-ticked]')].map(e => e.dataset.ticked + '/' + e.dataset.pass),
  }))()`);
  console.log(JSON.stringify(state));
  await page.screenshot(`${out}/journey-${tag}-end.png`);

  const toggled = await page.clickText("Base model");
  console.log("toggled base:", toggled);
  await sleep(500);
  await page.screenshot(`${out}/journey-${tag}-base.png`, { fullPage: true });
  if (page.console.length) console.log("console:", page.console.filter((c) => !/api\/health/.test(c)));
  await page.close();
} finally {
  await chrome.close();
}
