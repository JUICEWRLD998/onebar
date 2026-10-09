import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, getTrace, sendMessage, waitForReply } from "./api";
import { getPlace, getSession, parsePlaceReply, setPlace } from "./session";
import type { Message, Trace } from "./types";

interface State {
  messages: Message[];
  place: string | null;
}

type Action =
  | { type: "add"; message: Message }
  | { type: "patch"; id: string; patch: Partial<Message> }
  | { type: "place"; place: string | null };

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "add":
      return { ...state, messages: [...state.messages, action.message] };
    case "patch":
      return { ...state, messages: state.messages.map((m) => (m.id === action.id ? { ...m, ...action.patch } : m)) };
    case "place":
      return { ...state, place: action.place };
  }
}

export interface Deps {
  send: typeof sendMessage;
  wait: typeof waitForReply;
  trace: typeof getTrace;
  session: () => string;
  pause: (ms: number) => Promise<void>;
}

const defaultDeps: Deps = {
  send: sendMessage,
  wait: waitForReply,
  trace: getTrace,
  session: getSession,
  pause: (ms) => new Promise((r) => setTimeout(r, ms)),
};

export interface Conversation {
  messages: Message[];
  place: string | null;
  pending: boolean;
  send: (text: string) => Promise<void>;
  /** Set where the hiker is. Resolves with the server's own words so the picker can show them. */
  setPlace: (name: string) => Promise<{ ok: boolean; text: string }>;
  /** Play a recorded example through the same thread, clearly marked as recorded. */
  replay: (example: Trace) => Promise<void>;
  /** The audit of this reply has played; stop treating it as new. */
  markSeen: (id: string) => void;
}

let counter = 0;
const uid = (p: string) => `${p}${Date.now().toString(36)}${(counter++).toString(36)}`;

export function useConversation(deps: Deps = defaultDeps): Conversation {
  const [state, dispatch] = useReducer(reducer, undefined, () => ({ messages: [], place: getPlace() }) as State);
  const alive = useRef(true);
  const controller = useRef<AbortController>(new AbortController());
  useEffect(() => {
    alive.current = true;
    controller.current = new AbortController();
    return () => {
      alive.current = false;
      controller.current.abort();
    };
  }, []);

  const patch = useCallback((id: string, p: Partial<Message>) => {
    if (alive.current) dispatch({ type: "patch", id, patch: p });
  }, []);
  const add = useCallback((message: Message) => {
    if (alive.current) dispatch({ type: "add", message });
  }, []);

  /** Send one text to the service and fill in the placeholder `replyId` with whatever comes back. */
  const run = useCallback(
    async (text: string, replyId: string): Promise<{ ok: boolean; text: string }> => {
      try {
        const id = await deps.send(deps.session(), text);
        const { text: reply, traceId } = await deps.wait(id, { signal: controller.current.signal });
        let trace: Trace | undefined;
        if (traceId) {
          try {
            trace = await deps.trace(traceId, fetch, controller.current.signal);
          } catch {
            trace = undefined; // the reply still stands; only its audit is missing
          }
        }
        const placeName = parsePlaceReply(reply);
        if (placeName) {
          setPlace(placeName);
          if (alive.current) dispatch({ type: "place", place: placeName });
        }
        patch(replyId, { text: reply, status: "done", traceId: traceId ?? undefined, trace, fresh: Boolean(trace) });
        return { ok: true, text: reply };
      } catch (e) {
        if ((e as Error).name === "AbortError") return { ok: false, text: "" };
        const msg = e instanceof ApiError ? e.message : new ApiError("down").message;
        patch(replyId, { text: msg, status: "error" });
        return { ok: false, text: msg };
      }
    },
    [deps, patch],
  );

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text) return;
      add({ id: uid("y"), role: "you", text, status: "done" });
      const replyId = uid("r");
      add({ id: replyId, role: "reply", text: "", status: "pending" });
      await run(text, replyId);
    },
    [add, run],
  );

  const setPlaceByName = useCallback(
    async (name: string) => {
      const n = name.trim();
      if (!n) return { ok: false, text: "Type a place name, or coordinates like 46.55, 7.98." };
      const replyId = uid("n");
      add({ id: replyId, role: "note", text: "", status: "pending" });
      const res = await run(`PLACE ${n}`, replyId);
      return { ok: res.ok && parsePlaceReply(res.text) !== null, text: res.text };
    },
    [add, run],
  );

  const replay = useCallback(
    async (example: Trace) => {
      add({ id: uid("y"), role: "you", text: example.question, status: "done", recorded: true });
      const replyId = uid("r");
      add({ id: replyId, role: "reply", text: "", status: "pending", recorded: true });
      await deps.pause(650);
      patch(replyId, { text: example.reply, status: "done", trace: example, recorded: true, fresh: true });
    },
    [add, deps, patch],
  );

  const markSeen = useCallback((id: string) => patch(id, { fresh: false }), [patch]);

  return {
    messages: state.messages,
    place: state.place,
    pending: state.messages.some((m) => m.status === "pending"),
    send,
    setPlace: setPlaceByName,
    replay,
    markSeen,
  };
}
