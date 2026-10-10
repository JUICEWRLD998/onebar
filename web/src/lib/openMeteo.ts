/**
 * The browser looks up the place and the forecast itself and sends them with the message.
 *
 * Open-Meteo counts its free quota per IP. A shared cloud host's outbound IP is often over it before OneBar makes a
 * single call; the visitor's own connection is not. So the page fetches the same URLs the server would
 * (onebar/facts/open_meteo.py, onebar/facts/locate.py) and the server uses that copy for this session only, after
 * checking its shape (onebar/channels/hints.py). Every lookup here is optional: on any failure the message goes
 * without a hint and the server fetches for itself.
 */

type Fetch = typeof fetch;

export interface Pos {
  lat: number;
  lon: number;
}

export interface Hint {
  place?: { query: string; name: string; lat: number; lon: number };
  forecast?: { lat: number; lon: number; data: unknown };
}

// Keep in step with HOURLY and DAILY in onebar/facts/open_meteo.py.
const HOURLY =
  "temperature_2m,apparent_temperature,precipitation_probability,precipitation," +
  "weather_code,wind_speed_10m,wind_gusts_10m,cape";
const DAILY = "sunrise,sunset";
const TIMEOUT_MS = 8000;
const FORECAST_TTL_MS = 10 * 60 * 1000;

export function forecastUrl(lat: number, lon: number, days = 3): string {
  return (
    `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&hourly=${HOURLY}&daily=${DAILY}` +
    `&timezone=auto&forecast_days=${days}`
  );
}

export function geocodeUrl(name: string): string {
  return `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(name.trim())}&count=1&language=en&format=json`;
}

/** "46.02, 7.75" -> {lat, lon}, the same shape the server's PLACE and TRIP commands accept. */
export function parseCoords(text: string): Pos | null {
  const m = /^(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)$/.exec(text.trim());
  if (!m) return null;
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lat, lon } : null;
}

/** The place words inside PLACE or TRIP, or null for anything else. Mirrors onebar/commands.py. */
export function placeWords(text: string): string | null {
  const t = text.trim();
  const trip = /^trip\s+(.+?)\s+back\s+\S+\s+contact\s+.+$/is.exec(t);
  if (trip) return trip[1]!.trim();
  const place = /^place\s+(.{1,80})$/i.exec(t);
  return place ? place[1]!.trim() : null;
}

async function getJson(url: string, f: Fetch): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await f(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/** The best match for a place name, labelled the way the server labels it ("Zermatt, Switzerland"). */
export async function geocode(name: string, f: Fetch = fetch): Promise<Hint["place"] | null> {
  const body = (await getJson(geocodeUrl(name), f)) as { results?: Record<string, unknown>[] } | null;
  const r = body?.results?.[0];
  if (!r || typeof r.latitude !== "number" || typeof r.longitude !== "number") return null;
  const label = [r.name, r.country].filter((x): x is string => typeof x === "string" && x.length > 0).join(", ");
  return { query: name.trim(), name: label || name.trim(), lat: r.latitude, lon: r.longitude };
}

const forecasts = new Map<string, { at: number; data: unknown }>();

export async function fetchForecast(pos: Pos, f: Fetch = fetch, now: () => number = Date.now): Promise<unknown> {
  const key = `${pos.lat},${pos.lon}`;
  const hit = forecasts.get(key);
  if (hit && now() - hit.at < FORECAST_TTL_MS) return hit.data;
  const data = await getJson(forecastUrl(pos.lat, pos.lon), f);
  if (!data || typeof data !== "object" || (data as { error?: unknown }).error) throw new Error("no forecast");
  forecasts.set(key, { at: now(), data });
  return data;
}

export function clearForecastCache(): void {
  forecasts.clear();
}

/**
 * What to send along with `text`. A PLACE or TRIP message carries the place lookup and that place's forecast; a
 * question carries the forecast for `current`, the spot the server last confirmed. OUT, FORGET and HELP carry nothing.
 */
export async function browserHint(text: string, current: Pos | null, f: Fetch = fetch): Promise<Hint | undefined> {
  if (/^(out|forget|help)\b/i.test(text.trim())) return undefined;
  const words = placeWords(text);
  const hint: Hint = {};
  let pos: Pos | null = current;
  if (words !== null) {
    pos = parseCoords(words);
    if (!pos) {
      const place = await geocode(words, f).catch(() => null);
      if (!place) return undefined;
      hint.place = place;
      pos = { lat: place.lat, lon: place.lon };
    }
  }
  if (!pos) return undefined;
  try {
    hint.forecast = { lat: pos.lat, lon: pos.lon, data: await fetchForecast(pos, f) };
  } catch {
    /* the place lookup alone still helps */
  }
  return hint.place || hint.forecast ? hint : undefined;
}

/** Where a hint says the hiker is: the looked-up place, else the forecast's spot. */
export function hintPos(hint: Hint | undefined): Pos | null {
  const p = hint?.place ?? hint?.forecast;
  return p ? { lat: p.lat, lon: p.lon } : null;
}
