export interface Pt {
  x: number;
  y: number;
}

const r1 = (v: number) => Math.round(v * 10) / 10;
const dist = (a: Pt, b: Pt) => Math.hypot(b.x - a.x, b.y - a.y);

/** A polyline with each corner rounded by up to `radius`, never more than half of either neighbouring segment. */
export function roundedPolyline(points: Pt[], radius: number): string {
  if (points.length === 0) return "";
  const first = points[0] as Pt;
  let d = `M${r1(first.x)} ${r1(first.y)}`;
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1] as Pt;
    const cur = points[i] as Pt;
    const next = points[i + 1] as Pt;
    const din = dist(prev, cur);
    const dout = dist(cur, next);
    const cut = Math.min(radius, din / 2, dout / 2);
    if (cut <= 0.01 || din === 0 || dout === 0) {
      d += `L${r1(cur.x)} ${r1(cur.y)}`;
      continue;
    }
    const a = { x: cur.x - ((cur.x - prev.x) / din) * cut, y: cur.y - ((cur.y - prev.y) / din) * cut };
    const b = { x: cur.x + ((next.x - cur.x) / dout) * cut, y: cur.y + ((next.y - cur.y) / dout) * cut };
    d += `L${r1(a.x)} ${r1(a.y)}Q${r1(cur.x)} ${r1(cur.y)} ${r1(b.x)} ${r1(b.y)}`;
  }
  if (points.length > 1) {
    const last = points[points.length - 1] as Pt;
    d += `L${r1(last.x)} ${r1(last.y)}`;
  }
  return d;
}

/**
 * The leader line from a number in the reply to its row: drop below the number, run across the gutter, run along the
 * gutter to the row's height, then into the row. Four straight runs with rounded corners, like a map callout.
 */
export function leaderPath(start: Pt, end: Pt, gutterX: number, dropY: number, radius = 8): string {
  if (start.x >= gutterX) return roundedPolyline([start, end], 0); // no gutter to route through: go straight
  return roundedPolyline(
    [start, { x: start.x, y: dropY }, { x: gutterX, y: dropY }, { x: gutterX, y: end.y }, end],
    radius,
  );
}
