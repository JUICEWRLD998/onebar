// Zero-dependency Chrome DevTools Protocol driver (Node 22+: global fetch and WebSocket).
// Launches headless Chrome with a throwaway profile (deleted on close: profiles are 60-70 MB each) and exposes a
// small Page API: goto, evaluate, click by visible text, screenshot, device and colour-scheme emulation.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

const CHROME = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
].find((p) => p && existsSync(p));

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function launch({ port = 9444 } = {}) {
  if (!CHROME) throw new Error("no Chrome found; set CHROME_PATH");
  const profile = join(tmpdir(), `onebar-chrome-${Date.now()}-${port}`);
  const proc = spawn(
    CHROME,
    ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
      "--mute-audio", "--allow-file-access-from-files", `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank"],
    { stdio: "ignore" },
  );
  for (let i = 0; i < 80; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break;
    } catch {}
    await sleep(250);
  }
  const close = async () => {
    try { proc.kill(); } catch {}
    await sleep(400);
    try { rmSync(profile, { recursive: true, force: true }); } catch {}
  };
  return {
    port,
    close,
    async newPage() {
      const res = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" });
      const { webSocketDebuggerUrl, id } = await res.json();
      return Page.connect(webSocketDebuggerUrl, port, id);
    },
  };
}

export class Page {
  static async connect(wsUrl, port, id) {
    const ws = new WebSocket(wsUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    const p = new Page(ws, port, id);
    await p.send("Page.enable");
    await p.send("Runtime.enable");
    await p.send("Log.enable");
    return p;
  }

  constructor(ws, port, id) {
    this.ws = ws;
    this.port = port;
    this.id = id;
    this.n = 0;
    this.pending = new Map();
    this.handlers = new Map();
    this.console = [];
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { res, rej } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? rej(new Error(`${msg.error.message}`)) : res(msg.result);
      } else if (msg.method) {
        if (msg.method === "Runtime.consoleAPICalled" && ["error", "assert"].includes(msg.params.type))
          this.console.push(msg.params.args.map((a) => a.value ?? a.description).join(" "));
        if (msg.method === "Runtime.exceptionThrown") this.console.push("exception: " + (msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text));
        if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") this.console.push(`${msg.params.entry.source}: ${msg.params.entry.text} ${msg.params.entry.url ?? ""}`);
        (this.handlers.get(msg.method) ?? []).forEach((h) => h(msg.params));
      }
    };
  }

  send(method, params = {}) {
    const id = ++this.n;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }

  on(method, fn) {
    this.handlers.set(method, [...(this.handlers.get(method) ?? []), fn]);
  }

  async emulate({ width, height = 900, scheme = "light", reducedMotion = false, scale = 1 }) {
    await this.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile: width < 500 });
    const features = [{ name: "prefers-color-scheme", value: scheme }];
    if (reducedMotion) features.push({ name: "prefers-reduced-motion", value: "reduce" });
    else features.push({ name: "prefers-reduced-motion", value: "no-preference" });
    await this.send("Emulation.setEmulatedMedia", { features });
  }

  async goto(url, { settle = 600 } = {}) {
    const loaded = new Promise((r) => this.on("Page.loadEventFired", r));
    await this.send("Page.navigate", { url });
    await Promise.race([loaded, sleep(15000)]);
    await this.evaluate("document.fonts ? document.fonts.ready.then(() => true) : true");
    await sleep(settle);
  }

  async evaluate(expression) {
    const r = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  }

  /** Click the first visible element whose text matches exactly (case-insensitive) among buttons, links, tabs. */
  async clickText(text) {
    const ok = await this.evaluate(`(() => {
      const want = ${JSON.stringify(text)}.toLowerCase();
      const els = [...document.querySelectorAll('button, a, [role=button], [role=tab], summary, label')];
      const el = els.find((e) => e.offsetParent !== null && e.textContent.trim().toLowerCase() === want);
      if (!el) return false;
      el.scrollIntoView({block: 'center'}); el.click(); return true; })()`);
    if (!ok) throw new Error(`no visible control with text "${text}"`);
  }

  async type(selector, text) {
    await this.evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); el.focus();
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', {bubbles: true})); })()`);
  }

  async screenshot(file, { fullPage = false, format = "png", quality = 80 } = {}) {
    mkdirSync(dirname(file), { recursive: true });
    const params = { format, ...(format === "jpeg" ? { quality } : {}) };
    if (fullPage) {
      const m = await this.send("Page.getLayoutMetrics");
      const { width, height } = m.cssContentSize ?? m.contentSize;
      params.clip = { x: 0, y: 0, width, height: Math.min(height, 12000), scale: 1 };
      params.captureBeyondViewport = true;
    }
    const { data } = await this.send("Page.captureScreenshot", params);
    writeFileSync(file, Buffer.from(data, "base64"));
    return file;
  }

  async close() {
    try { this.ws.close(); } catch {}
    try { await fetch(`http://127.0.0.1:${this.port}/json/close/${this.id}`); } catch {}
  }
}
