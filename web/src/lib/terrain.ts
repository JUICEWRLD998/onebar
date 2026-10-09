/**
 * Real terrain to contour lines. Elevations come from Open-Meteo's elevation API for a small grid around a place;
 * everything after that is plain geometry: smooth the grid, run marching squares per level, chain the segments
 * into polylines, round the corners, emit SVG path data. No map library, no tiles, no image files.
 */

export interface Grid {
  rows: number;
  cols: number;
  z: number[]; // row-major, row 0 is the north edge
}

export interface Contours {
  width: number;
  height: number;
  minor: string; // SVG path data
  major: string; // every fifth level, drawn heavier
  levels: number[];
  interval: number;
  min: number;
  max: number;
  /** Highest grid cell, in view coordinates, for the spot-height mark. */
  summit: { x: number; y: number; z: number };
  /** The grid centre, where the place is. */
  centre: { x: number; y: number; z: number };
}

export const GRID_COLS = 12;
export const GRID_ROWS = 8;
export const GRID_STEP_DEG = 0.01; // about 1.1 km north to south

type Pt = [number, number];
type Seg = { a: string; b: string; pa: Pt; pb: Pt };

const at = (g: Grid, r: number, c: number) => g.z[r * g.cols + c] as number;
const same = (a: Pt, b: Pt) => Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;
const round = (v: number, d = 1) => Math.round(v * 10 ** d) / 10 ** d;

/** Coordinates of the grid points, row-major from the north-west corner, cells roughly square on the ground. */
export function gridPoints(lat: number, lon: number): { lats: number[]; lons: number[] } {
  const dLat = GRID_STEP_DEG;
  const dLon = GRID_STEP_DEG / Math.max(0.2, Math.cos((lat * Math.PI) / 180));
  const lats: number[] = [];
  const lons: number[] = [];
  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < GRID_COLS; c++) {
      lats.push(round(lat + ((GRID_ROWS - 1) / 2 - r) * dLat, 5));
      lons.push(round(lon + (c - (GRID_COLS - 1) / 2) * dLon, 5));
    }
  }
  return { lats, lons };
}

export function elevationUrl(lat: number, lon: number): string {
  const { lats, lons } = gridPoints(lat, lon);
  return `https://api.open-meteo.com/v1/elevation?latitude=${lats.join(",")}&longitude=${lons.join(",")}`;
}

export function parseElevation(payload: unknown): Grid {
  const z = (payload as { elevation?: unknown } | null)?.elevation;
  if (!Array.isArray(z) || z.length !== GRID_ROWS * GRID_COLS || z.some((v) => typeof v !== "number" || !Number.isFinite(v))) {
    throw new Error("elevation response has the wrong shape");
  }
  return { rows: GRID_ROWS, cols: GRID_COLS, z: z as number[] };
}

/** Catmull-Rom interpolation for a fractional position t in [0, 1) between samples p1 and p2. */
function cubic(p0: number, p1: number, p2: number, p3: number, t: number): number {
  return (
    0.5 *
    (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)
  );
}

/** Smooth upsampling so contours curve instead of following the coarse grid. Rows and columns grow by `factor`. */
export function upsample(g: Grid, factor: number): Grid {
  const rows = (g.rows - 1) * factor + 1;
  const cols = (g.cols - 1) * factor + 1;
  const clampR = (r: number) => Math.min(g.rows - 1, Math.max(0, r));
  const clampC = (c: number) => Math.min(g.cols - 1, Math.max(0, c));
  const tmp = new Array<number>(g.rows * cols); // columns first
  for (let r = 0; r < g.rows; r++) {
    for (let c = 0; c < cols; c++) {
      const c1 = Math.floor(c / factor);
      const t = (c % factor) / factor;
      tmp[r * cols + c] = cubic(at(g, r, clampC(c1 - 1)), at(g, r, c1), at(g, r, clampC(c1 + 1)), at(g, r, clampC(c1 + 2)), t);
    }
  }
  const z = new Array<number>(rows * cols);
  for (let r = 0; r < rows; r++) {
    const r1 = Math.floor(r / factor);
    const t = (r % factor) / factor;
    for (let c = 0; c < cols; c++) {
      const p = (rr: number) => tmp[clampR(rr) * cols + c] as number;
      z[r * cols + c] = cubic(p(r1 - 1), p(r1), p(r1 + 1), p(r1 + 2), t);
    }
  }
  return { rows, cols, z };
}

const NICE = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500];

/** A "nice" contour interval giving about `target` lines across the range, and the levels themselves. */
export function contourLevels(min: number, max: number, target = 24): { levels: number[]; interval: number } {
  const range = max - min;
  if (!(range > 0.5)) return { levels: [], interval: 0 };
  const raw = range / target;
  const interval = NICE.find((n) => n >= raw) ?? 500;
  const levels: number[] = [];
  for (let v = Math.ceil((min + 1e-6) / interval) * interval; v < max - 1e-6; v += interval) levels.push(v);
  return { levels, interval };
}

/** Segments of the iso-line at `level`, each tagged with the identity of the two cell edges it joins. */
export function segments(g: Grid, level: number): Seg[] {
  const out: Seg[] = [];
  const edgePoint = (kind: "h" | "v", r: number, c: number): Pt => {
    if (kind === "h") {
      const z1 = at(g, r, c);
      const z2 = at(g, r, c + 1);
      return [c + (level - z1) / (z2 - z1), r];
    }
    const z1 = at(g, r, c);
    const z2 = at(g, r + 1, c);
    return [c, r + (level - z1) / (z2 - z1)];
  };
  for (let r = 0; r < g.rows - 1; r++) {
    for (let c = 0; c < g.cols - 1; c++) {
      const a = at(g, r, c);
      const b = at(g, r, c + 1);
      const cc = at(g, r + 1, c + 1);
      const d = at(g, r + 1, c);
      let idx = 0;
      if (a >= level) idx |= 1;
      if (b >= level) idx |= 2;
      if (cc >= level) idx |= 4;
      if (d >= level) idx |= 8;
      if (idx === 0 || idx === 15) continue;
      const T = { id: `h${r},${c}`, p: () => edgePoint("h", r, c) };
      const R = { id: `v${r},${c + 1}`, p: () => edgePoint("v", r, c + 1) };
      const B = { id: `h${r + 1},${c}`, p: () => edgePoint("h", r + 1, c) };
      const L = { id: `v${r},${c}`, p: () => edgePoint("v", r, c) };
      const add = (e1: typeof T, e2: typeof T) => out.push({ a: e1.id, b: e2.id, pa: e1.p(), pb: e2.p() });
      const centreHigh = (a + b + cc + d) / 4 >= level;
      switch (idx) {
        case 1: case 14: add(L, T); break;
        case 2: case 13: add(T, R); break;
        case 3: case 12: add(L, R); break;
        case 4: case 11: add(R, B); break;
        case 6: case 9: add(T, B); break;
        case 7: case 8: add(L, B); break;
        case 5: if (centreHigh) { add(L, B); add(T, R); } else { add(L, T); add(R, B); } break;
        case 10: if (centreHigh) { add(L, T); add(R, B); } else { add(L, B); add(T, R); } break;
      }
    }
  }
  return out;
}

/** Join segments that share a cell edge into polylines (a closed line repeats its first point at the end). */
export function chain(segs: Seg[]): Pt[][] {
  const byEdge = new Map<string, number[]>();
  segs.forEach((s, i) => {
    for (const k of [s.a, s.b]) {
      const list = byEdge.get(k);
      if (list) list.push(i);
      else byEdge.set(k, [i]);
    }
  });
  const used = new Array<boolean>(segs.length).fill(false);
  const walk = (start: number, forward: boolean): Pt[] => {
    const pts: Pt[] = [];
    const first = segs[start] as Seg;
    let edge = forward ? first.b : first.a;
    for (;;) {
      const next = (byEdge.get(edge) ?? []).find((i) => !used[i]);
      if (next === undefined) break;
      used[next] = true;
      const s = segs[next] as Seg;
      if (s.a === edge) {
        pts.push(s.pb);
        edge = s.b;
      } else {
        pts.push(s.pa);
        edge = s.a;
      }
    }
    return pts;
  };
  const lines: Pt[][] = [];
  for (let i = 0; i < segs.length; i++) {
    if (used[i]) continue;
    used[i] = true;
    const s = segs[i] as Seg;
    const ahead = walk(i, true);
    const behind = walk(i, false);
    lines.push([...behind.reverse(), s.pa, s.pb, ...ahead]);
  }
  return lines;
}

/** Corner cutting; closed lines stay closed. */
export function chaikin(line: Pt[], passes = 1): Pt[] {
  let pts = line;
  for (let p = 0; p < passes; p++) {
    if (pts.length < 3) return pts;
    const closed = same(pts[0] as Pt, pts[pts.length - 1] as Pt);
    const out: Pt[] = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i] as Pt;
      const [x1, y1] = pts[i + 1] as Pt;
      out.push([0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1], [0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1]);
    }
    if (closed) out.push(out[0] as Pt);
    else {
      out.unshift(pts[0] as Pt);
      out.push(pts[pts.length - 1] as Pt);
    }
    pts = out;
  }
  return pts;
}

function pathData(lines: Pt[][], scale: number): string {
  return lines
    .filter((l) => l.length >= 2)
    .map((l) => {
      const closed = same(l[0] as Pt, l[l.length - 1] as Pt);
      const body = l.map(([x, y], i) => `${i === 0 ? "M" : "L"}${round(x * scale)} ${round(y * scale)}`).join("");
      return closed ? `${body}Z` : body;
    })
    .join("");
}

/** The whole job: elevation grid in, drawable contours out. `width` is the view width; height follows the grid. */
export function contoursFromGrid(coarse: Grid, width = 440, factor = 6): Contours {
  const g = upsample(coarse, factor);
  const scale = width / (g.cols - 1);
  const height = round(scale * (g.rows - 1));
  const min = Math.min(...g.z);
  const max = Math.max(...g.z);
  const { levels, interval } = contourLevels(min, max);
  const minor: Pt[][] = [];
  const major: Pt[][] = [];
  for (const level of levels) {
    const lines = chain(segments(g, level)).map((l) => chaikin(l, 1));
    // index lines sit at every fifth multiple of the interval, as on a printed map
    (Math.round(level / interval) % 5 === 0 ? major : minor).push(...lines);
  }
  let hi = 0;
  g.z.forEach((v, i) => {
    if (v > (g.z[hi] as number)) hi = i;
  });
  const cr = Math.round(((coarse.rows - 1) / 2) * factor);
  const cc = Math.round(((coarse.cols - 1) / 2) * factor);
  return {
    width,
    height,
    minor: pathData(minor, scale),
    major: pathData(major, scale),
    levels,
    interval,
    min: Math.round(min),
    max: Math.round(max),
    summit: { x: round((hi % g.cols) * scale), y: round(Math.floor(hi / g.cols) * scale), z: Math.round(g.z[hi] as number) },
    centre: { x: round(cc * scale), y: round(cr * scale), z: Math.round(g.z[cr * g.cols + cc] as number) },
  };
}

export async function fetchContours(
  lat: number,
  lon: number,
  doFetch: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<Contours> {
  const res = await doFetch(elevationUrl(lat, lon), { signal });
  if (!res.ok) throw new Error(`elevation request failed: ${res.status}`);
  return contoursFromGrid(parseElevation(await res.json()));
}
