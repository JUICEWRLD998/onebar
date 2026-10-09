import { useEffect, useState } from "react";
import { recordedContours } from "../data/recorded";
import { fetchContours, type Contours } from "../lib/terrain";
import type { Trace } from "../lib/types";

export type ContourStatus = "idle" | "loading" | "ready" | "error";

const memory = new Map<string, Contours>();
const keyOf = (lat: number, lon: number) => `onebar-terrain:${lat.toFixed(2)},${lon.toFixed(2)}`;

function fromSession(key: string): Contours | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Contours) : null;
  } catch {
    return null;
  }
}

function toSession(key: string, c: Contours): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(c));
  } catch {
    /* a full or blocked store only costs a refetch */
  }
}

/**
 * The terrain for a trace. A recorded example uses its built-in contours; a live one asks the elevation service for
 * a small grid around the place, once per place and session.
 */
export function useContours(trace: Trace | null): { contours: Contours | null; status: ContourStatus } {
  const [state, setState] = useState<{ contours: Contours | null; status: ContourStatus }>({ contours: null, status: "idle" });
  const id = trace?.id;
  const recorded = trace?.recorded;
  const lat = trace?.place?.lat;
  const lon = trace?.place?.lon;

  useEffect(() => {
    if (!trace) {
      setState({ contours: null, status: "idle" });
      return;
    }
    if (recorded && id) {
      const c = recordedContours(id);
      setState({ contours: c, status: c ? "ready" : "error" });
      return;
    }
    if (lat === undefined || lon === undefined) {
      setState({ contours: null, status: "idle" });
      return;
    }
    const key = keyOf(lat, lon);
    const hit = memory.get(key) ?? fromSession(key);
    if (hit) {
      memory.set(key, hit);
      setState({ contours: hit, status: "ready" });
      return;
    }
    const ac = new AbortController();
    setState({ contours: null, status: "loading" });
    fetchContours(lat, lon, fetch, ac.signal)
      .then((c) => {
        memory.set(key, c);
        toSession(key, c);
        setState({ contours: c, status: "ready" });
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setState({ contours: null, status: "error" });
      });
    return () => ac.abort();
    // trace identity is what matters; the fields above are its inputs
  }, [trace === null, id, recorded, lat, lon]); // eslint-disable-line react-hooks/exhaustive-deps

  return state;
}
