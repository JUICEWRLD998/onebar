// Browser storage can be missing, full or blocked (private windows, embedded previews). Every access is wrapped,
// and the app works without it: the session then lasts until the tab closes.
const memory = new Map<string, string>();

export function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key); // storage works: it is the truth, even when it holds nothing
  } catch {
    return memory.get(key) ?? null; // storage is blocked: fall back to what this tab has written
  }
}

export function safeSet(key: string, value: string): void {
  memory.set(key, value);
  try {
    localStorage.setItem(key, value);
  } catch {
    /* kept in memory only */
  }
}

export function safeRemove(key: string): void {
  memory.delete(key);
  try {
    localStorage.removeItem(key);
  } catch {
    /* nothing to do */
  }
}

const SESSION_KEY = "onebar-session";
const PLACE_KEY = "onebar-place";
const POS_KEY = "onebar-place-pos";

function randomId(length = 20): string {
  const bytes = new Uint8Array(length);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(bytes);
  else for (let i = 0; i < length; i++) bytes[i] = Math.floor(Math.random() * 256);
  return Array.from(bytes, (b) => (b % 36).toString(36)).join("");
}

/** An anonymous id the server uses to keep one visitor's place and thread together. 8 to 64 characters of [a-z0-9]. */
export function getSession(): string {
  const existing = safeGet(SESSION_KEY);
  if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
  const fresh = randomId();
  safeSet(SESSION_KEY, fresh);
  return fresh;
}

export const getPlace = (): string | null => safeGet(PLACE_KEY);
export const setPlace = (name: string): void => safeSet(PLACE_KEY, name);
export const clearPlace = (): void => {
  safeRemove(PLACE_KEY);
  safeRemove(POS_KEY);
};

/** The coordinates the server confirmed for the place, so the page can fetch that spot's forecast itself. */
export function getPlacePos(): { lat: number; lon: number } | null {
  try {
    const p = JSON.parse(safeGet(POS_KEY) ?? "null") as { lat?: unknown; lon?: unknown } | null;
    return p && typeof p.lat === "number" && typeof p.lon === "number" ? { lat: p.lat, lon: p.lon } : null;
  } catch {
    return null;
  }
}

export function setPlacePos(pos: { lat: number; lon: number } | null): void {
  if (pos) safeSet(POS_KEY, JSON.stringify(pos));
  else safeRemove(POS_KEY);
}

/** "Place set: Zermatt, Switzerland. Ask your question." -> "Zermatt, Switzerland" */
export function parsePlaceReply(text: string): string | null {
  const m = /^Place set: (.+?)\. Ask your question\.$/.exec(text);
  return m ? (m[1] ?? null) : null;
}
