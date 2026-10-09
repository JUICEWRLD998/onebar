/** Shapes shared by the API (GET /api/trace/{id}) and the recorded examples. */

export interface NumberTrace {
  text: string;
  ok: boolean;
  /** [fact key, forecast hour as ISO local time or null]. A key of "question" means the number came from the hiker. */
  sources: [string, string | null][];
}

export interface Attempt {
  source: string;
  text: string;
  passed: boolean;
  reasons: string[];
  error: string | null;
}

export interface Hour {
  t: string; // 2026-08-19T21:00, the place's own clock
  temp: number | null;
  gust: number | null;
  pop: number | null;
  storm: boolean;
  rain: boolean;
}

export interface Baseline {
  text: string;
  passed: boolean;
  reasons: string[];
  septets: number;
  numbers: NumberTrace[];
}

export interface Place {
  lat: number;
  lon: number;
  name?: string;
  elevation?: string | null;
}

export type Path = "model" | "model-retry" | "template";

export interface Trace {
  question: string;
  reply: string;
  path: Path;
  septets: number;
  intents: string[];
  numbers: NumberTrace[];
  attempts: Attempt[];
  hours: Hour[];
  baseline: Baseline | null;
  place?: Place | null;
  created?: string;
  /** Present on recorded examples only. */
  recorded?: boolean;
  id?: string;
  at?: string;
}

export type Role = "you" | "reply" | "note";

export interface Message {
  id: string;
  role: Role;
  text: string;
  status: "pending" | "done" | "error";
  traceId?: string;
  trace?: Trace;
  recorded?: boolean;
  /** True from the moment a live reply lands until its audit has played once. */
  fresh?: boolean;
}

/** What is being audited on the sheet: the tuned reply, or the base model's draft for the same question. */
export interface Subject {
  text: string;
  septets: number;
  numbers: NumberTrace[];
  reasons: string[];
  passed: boolean;
}
