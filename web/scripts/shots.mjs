// Screenshot URLs at several widths and colour schemes.
//   node scripts/shots.mjs --out <dir> [--widths 1280,375] [--schemes light,dark] [--full] <url> [<url> ...]
// File names: <index>-<slug>-<scheme>-<width>.png
import { launch } from "./lib/cdp.mjs";

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? fallback : args[i + 1];
};
const out = opt("out", "shots");
const widths = opt("widths", "1280,375").split(",").map(Number);
const schemes = opt("schemes", "light,dark").split(",");
const full = args.includes("--full");
const urls = args.filter((a, i) => !a.startsWith("--") && !["--out", "--widths", "--schemes"].includes(args[i - 1]));

const chrome = await launch({ port: 9444 });
try {
  const page = await chrome.newPage();
  for (const [i, url] of urls.entries()) {
    const slug = url.split("/").pop().replace(/\.html?$/, "").replace(/[^a-z0-9-]/gi, "-") || "page";
    for (const scheme of schemes)
      for (const width of widths) {
        await page.emulate({ width, height: width < 500 ? 812 : 900, scheme });
        await page.goto(url);
        const file = await page.screenshot(`${out}/${i + 1}-${slug}-${scheme}-${width}.png`, { fullPage: full });
        console.log(file);
      }
  }
  if (page.console.length) console.log("console errors:", page.console);
  await page.close();
} finally {
  await chrome.close();
}
