import { beforeEach, describe, expect, it, vi } from "vitest";
import { browserHint, clearForecastCache, fetchForecast, forecastUrl, hintPos, parseCoords, placeWords } from "./openMeteo";

const FORECAST = { latitude: 46.02, longitude: 7.75, utc_offset_seconds: 7200, hourly: { time: [] }, daily: {} };
const ZERMATT = { results: [{ name: "Zermatt", country: "Switzerland", latitude: 46.02, longitude: 7.75 }] };

/** A fetch that answers by URL host, and records every URL it was asked for. */
function fakeFetch(answers: { geo?: unknown; fc?: unknown; fcStatus?: number }) {
  const urls: string[] = [];
  const f = vi.fn(async (url: string) => {
    urls.push(url);
    const geo = url.includes("geocoding-api");
    const body = geo ? answers.geo : answers.fc;
    const status = geo ? 200 : (answers.fcStatus ?? 200);
    return new Response(JSON.stringify(body ?? {}), { status });
  }) as unknown as typeof fetch;
  return { f, urls };
}

beforeEach(() => clearForecastCache());

describe("the URLs match the server's", () => {
  it("asks for exactly what onebar/facts/open_meteo.py forecast_url asks for", () => {
    expect(forecastUrl(46.55, 7.98)).toBe(
      "https://api.open-meteo.com/v1/forecast?latitude=46.55&longitude=7.98&hourly=temperature_2m,apparent_temperature," +
        "precipitation_probability,precipitation,weather_code,wind_speed_10m,wind_gusts_10m,cape&daily=sunrise,sunset" +
        "&timezone=auto&forecast_days=3",
    );
  });
});

describe("reading the command", () => {
  it("finds the place words in PLACE and TRIP, and nothing in a question", () => {
    expect(placeWords("PLACE Zermatt")).toBe("Zermatt");
    expect(placeWords("place  46.02, 7.75 ")).toBe("46.02, 7.75");
    expect(placeWords("TRIP Snowdon BACK 17:00 CONTACT a@b.co")).toBe("Snowdon");
    expect(placeWords("storm before 3?")).toBeNull();
  });
  it("reads coordinates the way the server does", () => {
    expect(parseCoords("46.02, 7.75")).toEqual({ lat: 46.02, lon: 7.75 });
    expect(parseCoords("-33.9,18.4")).toEqual({ lat: -33.9, lon: 18.4 });
    expect(parseCoords("95, 7")).toBeNull();
    expect(parseCoords("Zermatt")).toBeNull();
  });
});

describe("browserHint", () => {
  it("looks a named place up, labels it like the server, and fetches that spot's forecast", async () => {
    const { f, urls } = fakeFetch({ geo: ZERMATT, fc: FORECAST });
    const hint = await browserHint("PLACE Zermatt", null, f);
    expect(hint?.place).toEqual({ query: "Zermatt", name: "Zermatt, Switzerland", lat: 46.02, lon: 7.75 });
    expect(hint?.forecast).toEqual({ lat: 46.02, lon: 7.75, data: FORECAST });
    expect(urls[1]).toBe(forecastUrl(46.02, 7.75));
    expect(hintPos(hint)).toEqual({ lat: 46.02, lon: 7.75 });
  });

  it("skips the geocoder for coordinates", async () => {
    const { f, urls } = fakeFetch({ fc: FORECAST });
    const hint = await browserHint("PLACE 46.02, 7.75", null, f);
    expect(hint).toEqual({ forecast: { lat: 46.02, lon: 7.75, data: FORECAST } });
    expect(urls.every((u) => !u.includes("geocoding-api"))).toBe(true);
  });

  it("sends a question with the forecast for the confirmed spot, and nothing when there is no spot", async () => {
    const { f } = fakeFetch({ fc: FORECAST });
    expect(await browserHint("storm before 3?", { lat: 46.02, lon: 7.75 }, f)).toEqual({
      forecast: { lat: 46.02, lon: 7.75, data: FORECAST },
    });
    expect(await browserHint("storm before 3?", null, f)).toBeUndefined();
  });

  it("adds nothing to OUT, FORGET or HELP and makes no request", async () => {
    const { f, urls } = fakeFetch({ fc: FORECAST });
    for (const t of ["OUT", "forget", "HELP"]) expect(await browserHint(t, { lat: 1, lon: 2 }, f)).toBeUndefined();
    expect(urls).toEqual([]);
  });

  it("gives up quietly when the place is unknown, and keeps the place when only the forecast fails", async () => {
    expect(await browserHint("PLACE Nowhereville", null, fakeFetch({ geo: {} }).f)).toBeUndefined();
    const hint = await browserHint("PLACE Zermatt", null, fakeFetch({ geo: ZERMATT, fcStatus: 429 }).f);
    expect(hint?.place?.name).toBe("Zermatt, Switzerland");
    expect(hint?.forecast).toBeUndefined();
  });

  it("never sends an Open-Meteo error payload as a forecast", async () => {
    const { f } = fakeFetch({ fc: { error: true, reason: "limit" } });
    expect(await browserHint("storm?", { lat: 1, lon: 2 }, f)).toBeUndefined();
  });
});

describe("fetchForecast", () => {
  it("reuses a fresh copy and refetches a stale one", async () => {
    const { f, urls } = fakeFetch({ fc: FORECAST });
    let t = 0;
    await fetchForecast({ lat: 1, lon: 2 }, f, () => t);
    await fetchForecast({ lat: 1, lon: 2 }, f, () => t);
    expect(urls.length).toBe(1);
    t = 11 * 60 * 1000;
    await fetchForecast({ lat: 1, lon: 2 }, f, () => t);
    expect(urls.length).toBe(2);
  });
});
