import { describe, expect, it } from "vitest";
import {
  GRID_COLS,
  GRID_ROWS,
  chain,
  chaikin,
  contourLevels,
  contoursFromGrid,
  elevationUrl,
  fetchContours,
  gridPoints,
  parseElevation,
  segments,
  upsample,
  type Grid,
} from "./terrain";

const cone = (n = 41, peak = 100): Grid => {
  const z: number[] = [];
  const c = (n - 1) / 2;
  for (let r = 0; r < n; r++) for (let q = 0; q < n; q++) z.push(peak - Math.hypot(r - c, q - c));
  return { rows: n, cols: n, z };
};

describe("contourLevels", () => {
  it("picks a nice interval and levels strictly inside the range", () => {
    const { levels, interval } = contourLevels(1980, 3219);
    expect([50, 100]).toContain(interval);
    expect(levels.every((v) => v % interval === 0 && v > 1980 && v < 3219)).toBe(true);
    expect(levels.length).toBeGreaterThan(8);
    expect(levels.length).toBeLessThanOrEqual(20);
  });
  it("returns nothing for flat ground", () => {
    expect(contourLevels(500, 500).levels).toEqual([]);
    expect(contourLevels(500, 500.2).levels).toEqual([]);
  });
});

describe("marching squares", () => {
  it("turns a cone into one closed ring whose radius is the peak minus the level", () => {
    const lines = chain(segments(cone(41, 100), 90)); // radius 10, centred on (20, 20)
    expect(lines).toHaveLength(1);
    const ring = lines[0]!;
    expect(ring[0]).toEqual(ring[ring.length - 1]); // closed
    for (const [x, y] of ring) expect(Math.abs(Math.hypot(x - 20, y - 20) - 10)).toBeLessThan(0.4);
    expect(ring.length).toBeGreaterThan(30);
  });
  it("draws nothing when the level is outside the data", () => {
    expect(segments(cone(), 1000)).toEqual([]);
    expect(segments(cone(), -5)).toEqual([]);
  });
  it("draws one straight open line across a plane", () => {
    const z: number[] = [];
    for (let r = 0; r < 6; r++) for (let c = 0; c < 6; c++) z.push(c * 10);
    const lines = chain(segments({ rows: 6, cols: 6, z }, 25));
    expect(lines).toHaveLength(1);
    expect(lines[0]!.every(([x]) => Math.abs(x - 2.5) < 1e-9)).toBe(true);
    expect(lines[0]![0]).not.toEqual(lines[0]![lines[0]!.length - 1]);
  });
  it("resolves a saddle into two segments either way round", () => {
    const g: Grid = { rows: 2, cols: 2, z: [10, 0, 0, 10] };
    expect(segments(g, 5)).toHaveLength(2);
    expect(segments({ ...g, z: [0, 10, 10, 0] }, 5)).toHaveLength(2);
  });
  it("gives two lines for two separate hills", () => {
    const n = 41;
    const z: number[] = [];
    for (let r = 0; r < n; r++)
      for (let c = 0; c < n; c++) z.push(Math.max(30 - Math.hypot(r - 10, c - 10), 30 - Math.hypot(r - 30, c - 30)));
    expect(chain(segments({ rows: n, cols: n, z }, 22))).toHaveLength(2); // radius 8, well inside the grid
  });
});

describe("smoothing", () => {
  it("keeps closed lines closed and open lines pinned at their ends", () => {
    const closed = chaikin([[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], 2);
    expect(closed[0]).toEqual(closed[closed.length - 1]);
    const open = chaikin([[0, 0], [4, 0], [4, 4]], 2);
    expect(open[0]).toEqual([0, 0]);
    expect(open[open.length - 1]).toEqual([4, 4]);
  });
  it("upsamples a plane exactly in the interior and keeps the corners", () => {
    const z: number[] = [];
    for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) z.push(r * 100 + c * 10);
    const u = upsample({ rows: 4, cols: 4, z }, 4);
    expect(u.rows).toBe(13);
    expect(u.cols).toBe(13);
    expect(u.z[0]).toBeCloseTo(0);
    expect(u.z[u.z.length - 1]).toBeCloseTo(330);
    expect(u.z[6 * 13 + 6]).toBeCloseTo(165); // halfway between row 1 and 2, column 1 and 2: 150 + 15
  });
});

describe("contoursFromGrid", () => {
  const coarse: Grid = (() => {
    const z: number[] = [];
    for (let r = 0; r < GRID_ROWS; r++)
      for (let c = 0; c < GRID_COLS; c++) z.push(2000 + 1200 * Math.exp(-((r - 3) ** 2 + (c - 6) ** 2) / 8));
    return { rows: GRID_ROWS, cols: GRID_COLS, z };
  })();
  it("produces paths, index lines, a summit at the peak and a centre height", () => {
    const c = contoursFromGrid(coarse, 440);
    expect(c.width).toBe(440);
    expect(c.height).toBeCloseTo((440 * (GRID_ROWS - 1)) / (GRID_COLS - 1), 0);
    expect(c.minor.startsWith("M")).toBe(true);
    expect(c.major.startsWith("M")).toBe(true);
    expect(c.summit.z).toBeGreaterThan(3100);
    expect(c.centre.z).toBeGreaterThan(3000);
    expect(Math.abs(c.summit.x - 240)).toBeLessThan(10); // column 6 of 11
    expect(c.levels.length).toBeGreaterThan(5);
  });
  it("stays inside the view box", () => {
    const c = contoursFromGrid(coarse, 440);
    const nums = (c.minor + c.major).match(/-?\d+(\.\d+)?/g)!.map(Number);
    expect(Math.min(...nums)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...nums)).toBeLessThanOrEqual(440.1);
  });
  it("is deterministic", () => {
    expect(contoursFromGrid(coarse).minor).toBe(contoursFromGrid(coarse).minor);
  });
  it("handles flat ground without throwing", () => {
    const flat: Grid = { rows: GRID_ROWS, cols: GRID_COLS, z: new Array(GRID_ROWS * GRID_COLS).fill(430) };
    const c = contoursFromGrid(flat);
    expect(c.minor).toBe("");
    expect(c.levels).toEqual([]);
  });
});

describe("elevation request", () => {
  it("asks for 96 points, within the API's 100 limit, centred on the place", () => {
    const { lats, lons } = gridPoints(46.55, 7.98);
    expect(lats).toHaveLength(96);
    expect(Math.max(...lats)).toBeGreaterThan(46.55);
    expect(Math.min(...lats)).toBeLessThan(46.55);
    expect(Math.abs((Math.max(...lons) + Math.min(...lons)) / 2 - 7.98)).toBeLessThan(1e-4);
    const url = elevationUrl(46.55, 7.98);
    expect(url.startsWith("https://api.open-meteo.com/v1/elevation?latitude=")).toBe(true);
    expect(url).toContain("&longitude=");
  });
  it("widens the longitude step with latitude so cells stay square", () => {
    const eq = gridPoints(0, 0).lons;
    const hi = gridPoints(60, 0).lons;
    expect(Math.abs((hi[1]! - hi[0]!) / (eq[1]! - eq[0]!) - 2)).toBeLessThan(0.01);
  });
  it("rejects malformed payloads", () => {
    for (const bad of [null, {}, { elevation: [1, 2] }, { elevation: new Array(96).fill("x") }, { elevation: new Array(96).fill(NaN) }])
      expect(() => parseElevation(bad)).toThrow();
    expect(parseElevation({ elevation: new Array(96).fill(5) }).z).toHaveLength(96);
  });
  it("fetchContours surfaces HTTP errors and parses good responses", async () => {
    const ok = async () => new Response(JSON.stringify({ elevation: Array.from({ length: 96 }, (_, i) => 1000 + (i % 12) * 30) }));
    expect((await fetchContours(46.5, 7.9, ok as unknown as typeof fetch)).levels.length).toBeGreaterThan(0);
    const bad = async () => new Response("no", { status: 429 });
    await expect(fetchContours(46.5, 7.9, bad as unknown as typeof fetch)).rejects.toThrow("429");
  });
});
