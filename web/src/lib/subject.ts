import type { Subject, Trace } from "./types";

export type Model = "tuned" | "base";

/**
 * What the audit sheet is judging. The tuned reply is the one that went out, so it passed; the base model's draft is
 * the same question answered by the untuned model, with the checker's own verdict on it.
 */
export function subjectOf(trace: Trace, model: Model): Subject {
  if (model === "base" && trace.baseline) {
    const b = trace.baseline;
    return { text: b.text, septets: b.septets, numbers: b.numbers, reasons: b.reasons, passed: b.passed };
  }
  return { text: trace.reply, septets: trace.septets, numbers: trace.numbers, reasons: [], passed: true };
}
