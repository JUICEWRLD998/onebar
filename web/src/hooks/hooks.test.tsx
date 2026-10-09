import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { leaderPath, roundedPolyline } from "../lib/elbow";
import { audit } from "../lib/motion";
import { finalState, planSequence, useAuditSequence, START } from "./useAuditSequence";
import { useMediaQuery } from "./useMediaQuery";

function stubMatchMedia(matches: boolean) {
  const listeners = new Set<() => void>();
  const mq = {
    matches,
    media: "",
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  vi.stubGlobal("matchMedia", () => mq);
  return {
    set(next: boolean) {
      mq.matches = next;
      listeners.forEach((fn) => fn());
    },
  };
}

describe("planSequence", () => {
  it("follows the beat sheet for a reply with three numbers", () => {
    const steps = planSequence(3, 5);
    expect(steps[0]).toEqual({ at: audit.meterStart, patch: { meter: 1 } });
    const tokens = steps.filter((s) => s.patch.verified !== undefined);
    expect(tokens.map((s) => [s.at, s.patch.verified, s.patch.active])).toEqual([
      [240, 1, 0],
      [420, 2, 1],
      [600, 3, 2],
    ]);
    expect(steps.filter((s) => s.patch.ticks !== undefined).map((s) => s.patch.ticks)).toEqual([1, 2, 3, 4, 5]);
    const last = steps[steps.length - 1]!;
    expect(last.patch).toEqual({ done: true, active: 0 });
    expect(last.at).toBeGreaterThanOrEqual(audit.settle);
    expect(last.at).toBeLessThanOrEqual(1200); // settles by about a second
  });
  it("is in time order and never schedules a check before the numbers are checked", () => {
    const steps = planSequence(4, 5);
    expect(steps.map((s) => s.at)).toEqual([...steps.map((s) => s.at)].sort((a, b) => a - b));
    const lastToken = Math.max(...steps.filter((s) => s.patch.verified !== undefined).map((s) => s.at));
    const firstTick = Math.min(...steps.filter((s) => s.patch.ticks !== undefined).map((s) => s.at));
    expect(firstTick).toBeGreaterThan(lastToken);
  });
  it("animates at most four numbers and snaps the rest", () => {
    const steps = planSequence(7, 5);
    const tokens = steps.filter((s) => s.patch.verified !== undefined);
    expect(tokens.map((s) => s.patch.verified)).toEqual([1, 2, 3, 4, 7]);
  });
  it("still meters, ticks and settles when there are no numbers", () => {
    const steps = planSequence(0, 5);
    expect(steps.filter((s) => s.patch.verified !== undefined)).toEqual([]);
    expect(steps[steps.length - 1]!.patch).toEqual({ done: true, active: null });
  });
  it("final state is the same words as the end of the sequence", () => {
    expect(finalState(3, 5)).toEqual({ verified: 3, active: 0, meter: 1, ticks: 5, done: true });
    expect(finalState(0, 5).active).toBeNull();
  });
});

describe("useAuditSequence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    stubMatchMedia(false);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("walks from nothing checked to everything checked, then calls onDone once", () => {
    const onDone = vi.fn();
    const { result } = renderHook(() => useAuditSequence({ id: "a", play: true, numbers: 3, onDone }));
    expect(result.current).toEqual(START);
    act(() => void vi.advanceTimersByTime(250));
    expect(result.current).toMatchObject({ meter: 1, verified: 1, active: 0, done: false });
    act(() => void vi.advanceTimersByTime(200));
    expect(result.current).toMatchObject({ verified: 2, active: 1 });
    act(() => void vi.advanceTimersByTime(1000));
    expect(result.current).toEqual(finalState(3, 5));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
  it("shows the end state at once for anything that is not a fresh reply", () => {
    const { result } = renderHook(() => useAuditSequence({ id: "a", play: false, numbers: 3 }));
    expect(result.current).toEqual(finalState(3, 5));
  });
  it("shows the end state at once, with the same verdict inputs, when reduced motion is on", () => {
    stubMatchMedia(true);
    const onDone = vi.fn();
    const { result } = renderHook(() => useAuditSequence({ id: "a", play: true, numbers: 3, onDone }));
    expect(result.current).toEqual(finalState(3, 5));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
  it("restarts for a different reply and drops the old timers", () => {
    const onDone = vi.fn();
    const { result, rerender } = renderHook(({ id }) => useAuditSequence({ id, play: true, numbers: 2, onDone }), {
      initialProps: { id: "a" },
    });
    act(() => void vi.advanceTimersByTime(300));
    expect(result.current.verified).toBe(1);
    rerender({ id: "b" });
    expect(result.current.verified).toBe(0);
    act(() => void vi.advanceTimersByTime(2000));
    expect(result.current).toEqual(finalState(2, 5));
    expect(onDone).toHaveBeenCalledTimes(1); // only the second reply finished
  });
  it("jumps to the end state when the reply stops being new mid-sequence", () => {
    const { result, rerender } = renderHook(({ play }) => useAuditSequence({ id: "a", play, numbers: 3 }), {
      initialProps: { play: true },
    });
    act(() => void vi.advanceTimersByTime(300));
    rerender({ play: false });
    expect(result.current).toEqual(finalState(3, 5));
  });
});

describe("leader geometry", () => {
  const nums = (d: string) => d.match(/-?\d+(\.\d+)?/g)!.map(Number);
  it("starts at the number, ends at the row and goes through the gutter", () => {
    const d = leaderPath({ x: 100, y: 50 }, { x: 600, y: 400 }, 400, 70, 8);
    expect(d.startsWith("M100 50")).toBe(true);
    expect(d.endsWith("L600 400")).toBe(true);
    expect(nums(d).every(Number.isFinite)).toBe(true);
    expect(d).toContain("L392 70"); // arrives at the gutter corner, one radius short
    expect(d).toContain("Q400 70 400 78"); // the corner curves and leaves one radius further down
  });
  it("with radius 0 is a plain four-run polyline through each corner", () => {
    expect(roundedPolyline([{ x: 0, y: 0 }, { x: 0, y: 10 }, { x: 20, y: 10 }, { x: 20, y: 30 }, { x: 40, y: 30 }], 0)).toBe(
      "M0 0L0 10L20 10L20 30L40 30",
    );
  });
  it("never rounds more than half of a short segment", () => {
    const d = roundedPolyline([{ x: 0, y: 0 }, { x: 0, y: 4 }, { x: 100, y: 4 }], 8);
    expect(d).toContain("L0 2"); // cut limited to 2, not 8
  });
  it("goes straight when the number is already past the gutter", () => {
    expect(leaderPath({ x: 500, y: 10 }, { x: 600, y: 90 }, 400, 30)).toBe("M500 10L600 90");
  });
  it("handles an empty or single-point path without throwing", () => {
    expect(roundedPolyline([], 8)).toBe("");
    expect(roundedPolyline([{ x: 1, y: 2 }], 8)).toBe("M1 2");
  });
});

describe("useMediaQuery", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("follows the query as it changes", () => {
    const m = stubMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 64rem)"));
    expect(result.current).toBe(false);
    act(() => m.set(true));
    expect(result.current).toBe(true);
  });
  it("is false where matchMedia does not exist", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => useMediaQuery("(min-width: 64rem)"));
    expect(result.current).toBe(false);
  });
});
