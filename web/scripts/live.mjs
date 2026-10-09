// Drives the real stack through the browser: set a place, ask a question, wait for a live reply, read its audit.
//   node scripts/live.mjs --url http://localhost:4183 --out <dir> [--place Zermatt] [--ask "how windy is it going to get?"]
// Needs the API (uvicorn), the Temporal worker and Temporal dev server running. Costs a fraction of a cent per reply.
import { launch, sleep } from "./lib/cdp.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i === -1 ? d : args[i + 1];
};
const url = opt("url", "http://localhost:4183");
const out = opt("out", "shots");
const place = opt("place", "Zermatt");
const ask = opt("ask", "how windy is it going to get?");
const width = Number(opt("width", "1280"));

const waitFor = async (page, expr, ms, label) => {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await page.evaluate(expr)) return true;
    await sleep(400);
  }
  console.log(`TIMEOUT waiting for ${label}`);
  return false;
};

const chrome = await launch({ port: 9488 });
try {
  const page = await chrome.newPage();
  await page.emulate({ width, height: width < 500 ? 812 : 900, scheme: "light" });
  await page.goto(`${url}/?theme=light`);
  console.log("header:", await page.evaluate(`document.querySelector('header')?.innerText.replace(/\\s+/g, ' ')`));

  await page.type("#place-input", place);
  await page.clickText("Set place");
  const placed = await waitFor(page, `document.querySelector('[class*="placeName"]')?.textContent?.includes(${JSON.stringify(place)})`, 60000, "place set");
  console.log("place set:", placed, await page.evaluate(`document.querySelector('[class*="placeName"]')?.textContent`));
  await page.screenshot(`${out}/live-1-place.png`);

  await page.type("#ask-input", ask);
  await page.clickText("Send");
  const replied = await waitFor(page, `!!document.querySelector('button[class*="token"]') || !!document.querySelector('[class*="error"]')`, 90000, "reply");
  await sleep(1800);
  const state = await page.evaluate(`(() => ({
    reply: document.querySelector('[class*="reply"][data-selected]')?.textContent,
    tokens: [...document.querySelectorAll('button[class*="token"]')].map(b => b.textContent + ':' + b.dataset.state),
    verdict: document.querySelector('[class*="verdict"]')?.textContent,
    error: document.querySelector('[class*="error"]')?.textContent,
    sheetTitle: document.querySelector('#sheet-title')?.textContent,
    map: !!document.querySelector('figure svg'),
    mapEmpty: document.querySelector('[class*="mapEmpty"]')?.textContent,
    rows: [...document.querySelectorAll('[class*="row"][data-state]')].map(r => r.innerText.replace(/\\s+/g, ' ')),
    permalink: document.querySelector('a[href^="/trace/"]')?.getAttribute('href'),
    baseEnabled: [...document.querySelectorAll('button')].find(b => b.textContent === 'Base model')?.disabled === false,
  }))()`);
  console.log("replied:", replied);
  console.log(JSON.stringify(state, null, 1));
  await page.screenshot(`${out}/live-2-reply.png`);

  if (state.permalink) {
    await page.goto(`${url}${state.permalink}?theme=light`);
    await sleep(1500);
    console.log("trace page:", await page.evaluate(`document.querySelector('h1')?.textContent + ' | ' + document.querySelector('#sheet-title')?.textContent`));
    await page.screenshot(`${out}/live-3-trace.png`);
  }
  console.log("console:", page.console);
  await page.close();
} finally {
  await chrome.close();
}
