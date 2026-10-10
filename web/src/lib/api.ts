import type { Hint } from "./openMeteo";
import type { Trace } from "./types";

export type ApiErrorKind = "rate" | "toolong" | "down" | "bad";

const MESSAGES: Record<ApiErrorKind, string> = {
  rate: "Too many messages. Wait a few minutes, then try again.",
  toolong: "That is over 500 characters. Shorten it and send again.",
  down: "OneBar cannot be reached. Try again in a moment, or replay a recorded example.",
  bad: "That message could not be sent. Check it and try again.",
};

export class ApiError extends Error {
  constructor(public kind: ApiErrorKind) {
    super(MESSAGES[kind]);
  }
}

type Fetch = typeof fetch;

export const MAX_LEN = 500;

/** `hint` is what the browser looked up itself (see openMeteo.ts); the server checks it and may ignore it. */
export async function sendMessage(session: string, text: string, f: Fetch = fetch, hint?: Hint): Promise<string> {
  let res: Response;
  try {
    res = await f("/api/message", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(hint ? { session, text, hint } : { session, text }),
    });
  } catch {
    throw new ApiError("down");
  }
  if (res.status === 429) throw new ApiError("rate");
  if (res.status === 413) throw new ApiError("toolong");
  if (res.status === 422) throw new ApiError("bad");
  if (!res.ok) throw new ApiError("down");
  const body = (await res.json()) as { id?: string };
  if (!body.id) throw new ApiError("down");
  return body.id;
}

export type ReplyState = { status: "pending" } | { status: "done"; text: string; trace_id: string | null };

export async function getReply(id: string, f: Fetch = fetch, signal?: AbortSignal): Promise<ReplyState> {
  let res: Response;
  try {
    res = await f(`/api/reply/${encodeURIComponent(id)}`, { signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("down");
  }
  if (!res.ok) throw new ApiError(res.status === 404 ? "bad" : "down");
  return (await res.json()) as ReplyState;
}

export async function getTrace(traceId: string, f: Fetch = fetch, signal?: AbortSignal): Promise<Trace> {
  let res: Response;
  try {
    res = await f(`/api/trace/${encodeURIComponent(traceId)}`, { signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("down");
  }
  if (!res.ok) throw new ApiError(res.status === 404 ? "bad" : "down");
  return (await res.json()) as Trace;
}

export async function health(f: Fetch = fetch): Promise<boolean> {
  try {
    const res = await f("/api/health");
    return res.ok && ((await res.json()) as { ok?: boolean }).ok === true;
  } catch {
    return false;
  }
}

export interface WaitOptions {
  f?: Fetch;
  signal?: AbortSignal;
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Poll until the reply is there. Gives up with a "down" error after timeoutMs rather than waiting forever. */
export async function waitForReply(id: string, o: WaitOptions = {}): Promise<{ text: string; traceId: string | null }> {
  const { f = fetch, signal, intervalMs = 700, timeoutMs = 75_000, sleep = defaultSleep } = o;
  let waited = 0;
  let failures = 0;
  for (;;) {
    if (signal?.aborted) throw new DOMException("aborted", "AbortError");
    try {
      const r = await getReply(id, f, signal);
      failures = 0;
      if (r.status === "done") return { text: r.text, traceId: r.trace_id };
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
      if (++failures >= 4) throw e; // a few blips are fine, a dead service is not
    }
    if (waited >= timeoutMs) throw new ApiError("down");
    await sleep(intervalMs);
    waited += intervalMs;
  }
}
