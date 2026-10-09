import { useEffect, useMemo, useRef, useState } from "react";
import { audit, prefersReducedMotion } from "../lib/motion";

export interface AuditState {
  /** How many numbers have been checked so far. */
  verified: number;
  /** The number whose leader line is drawn, or null. */
  active: number | null;
  /** The length meter, 0 to 1 of its final fill. */
  meter: number;
  /** How many rows of the checks list have ticked. */
  ticks: number;
  done: boolean;
}

export interface Step {
  at: number; // ms after the reply lands
  patch: Partial<AuditState>;
}

export const START: AuditState = { verified: 0, active: null, meter: 0, ticks: 0, done: false };

export const finalState = (numbers: number, checks: number): AuditState => ({
  verified: numbers,
  active: numbers > 0 ? 0 : null, // at rest the first number is the one with its leader drawn
  meter: 1,
  ticks: checks,
  done: true,
});

/**
 * The beat sheet for the signature moment as data: the meter fills, each number is checked in turn (at most four
 * animate, the rest snap together), the checks tick, and the verdict settles by about a second.
 */
export function planSequence(numbers: number, checks: number): Step[] {
  const steps: Step[] = [{ at: audit.meterStart, patch: { meter: 1 } }];
  const animated = Math.min(numbers, audit.maxAnimatedTokens);
  for (let i = 0; i < animated; i++) steps.push({ at: audit.firstToken + i * audit.tokenGap, patch: { verified: i + 1, active: i } });
  let end = numbers > 0 ? audit.firstToken + (animated - 1) * audit.tokenGap : audit.meterStart;
  if (numbers > animated) {
    end += audit.tokenGap;
    steps.push({ at: end, patch: { verified: numbers, active: numbers - 1 } });
  }
  const checksStart = Math.max(end + 120, 700);
  for (let j = 0; j < checks; j++) steps.push({ at: checksStart + j * audit.checkGap, patch: { ticks: j + 1 } });
  const doneAt = Math.max(audit.settle, checksStart + (checks - 1) * audit.checkGap + 120);
  steps.push({ at: doneAt, patch: { done: true, active: numbers > 0 ? 0 : null } });
  return steps;
}

interface Options {
  /** Changes when a different reply is shown. */
  id: string;
  /** True only for a reply that has just landed and has not played yet. */
  play: boolean;
  numbers: number;
  checks?: number;
  onDone?: () => void;
}

/**
 * Drives the signature moment. Anything that is not a fresh reply, and everyone who prefers reduced motion, gets
 * the end state at once: the same numbers, the same verdict text, no movement.
 */
export function useAuditSequence({ id, play, numbers, checks = 5, onDone }: Options): AuditState {
  const final = useMemo(() => finalState(numbers, checks), [numbers, checks]);
  const [state, setState] = useState<AuditState>(play ? START : final);
  const done = useRef(onDone);
  done.current = onDone;
  const reduced = prefersReducedMotion();

  useEffect(() => {
    if (!play) {
      setState(final);
      return;
    }
    if (reduced) {
      setState(final);
      done.current?.();
      return;
    }
    setState(START);
    const timers = planSequence(numbers, checks).map((s) =>
      window.setTimeout(() => {
        setState((prev) => ({ ...prev, ...s.patch }));
        if (s.patch.done) done.current?.();
      }, s.at),
    );
    return () => timers.forEach(window.clearTimeout);
  }, [id, play, numbers, checks, final, reduced]);

  return !play || reduced ? final : state;
}
