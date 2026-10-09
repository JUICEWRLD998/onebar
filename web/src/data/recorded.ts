/**
 * Content for the empty states: recorded examples, example questions and quick places.
 * The recorded examples are real rows from the frozen test set (see scripts/make_web_examples.py): the question,
 * the tuned model's reply, the base model's draft, the checker's verdicts and the forecast hours the facts came from.
 */
import type { Contours } from "../lib/terrain";
import type { Trace } from "../lib/types";
import examples from "./examples.json";
import terrain from "./terrain.json";

export const recordedExamples = examples as unknown as Trace[];

export function recordedTrace(id: string): Trace | null {
  return recordedExamples.find((e) => e.id === id) ?? null;
}

export function recordedContours(id: string): Contours | null {
  return (terrain as unknown as Record<string, { contours: Contours }>)[id]?.contours ?? null;
}

/** Questions a hiker really sends, one per kind the checker knows. */
export const EXAMPLE_QUESTIONS = [
  "storm before 3?",
  "how windy is it going to get?",
  "do I need a headlamp?",
  "how cold will it get?",
];

/** Places to try without typing. The forecast and terrain for each are fetched live. */
export const QUICK_PLACES = ["Zermatt", "Snowdon", "Banff", "Mount Rainier", "Mount Fuji"];
