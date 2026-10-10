import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import examples from "../data/examples.json";
import { ApiError, getReply, getTrace, health, sendMessage, waitForReply } from "./api";
import { useConversation, type Deps } from "./conversation";
import { getSession, parsePlaceReply, safeGet, safeSet } from "./session";
import { applyTheme, nextTheme } from "./theme";
import type { Trace } from "./types";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const fetchOf = (...responses: (Response | Error)[]) => {
  const queue = [...responses];
  return vi.fn(async () => {
    const r = queue.length > 1 ? queue.shift() : queue[0];
    if (r instanceof Error) throw r;
    return r!.clone();
  }) as unknown as typeof fetch;
};
const calls = (f: typeof fetch) => (f as unknown as ReturnType<typeof vi.fn>).mock.calls;
const noSleep = async () => {};

describe("sendMessage", () => {
  it("posts the session and text and returns the message id", async () => {
    const f = fetchOf(json({ id: "abc" }));
    expect(await sendMessage("sess-12345678", "storm?", f)).toBe("abc");
    const [url, init] = calls(f)[0]!;
    expect(url).toBe("/api/message");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ session: "sess-12345678", text: "storm?" });
  });
  it.each([
    [429, "rate"],
    [413, "toolong"],
    [422, "bad"],
    [500, "down"],
    [503, "down"],
  ])("maps HTTP %i to %s", async (status, kind) => {
    await expect(sendMessage("s", "t", fetchOf(json({}, status)))).rejects.toMatchObject({ kind });
  });
  it("maps a network failure and a body without an id to down", async () => {
    await expect(sendMessage("s", "t", fetchOf(new TypeError("offline")))).rejects.toMatchObject({ kind: "down" });
    await expect(sendMessage("s", "t", fetchOf(json({})))).rejects.toMatchObject({ kind: "down" });
  });
  it("gives every error a message a hiker can act on", () => {
    for (const k of ["rate", "toolong", "down", "bad"] as const) expect(new ApiError(k).message.length).toBeGreaterThan(20);
  });
});

describe("reading replies and traces", () => {
  it("returns pending and done states", async () => {
    expect(await getReply("id", fetchOf(json({ status: "pending" })))).toEqual({ status: "pending" });
    expect(await getReply("id", fetchOf(json({ status: "done", text: "No storm.", trace_id: "t1" })))).toMatchObject({ text: "No storm." });
  });
  it("404 is bad, everything else is down", async () => {
    await expect(getReply("id", fetchOf(json({}, 404)))).rejects.toMatchObject({ kind: "bad" });
    await expect(getTrace("t", fetchOf(json({}, 404)))).rejects.toMatchObject({ kind: "bad" });
    await expect(getTrace("t", fetchOf(json({}, 502)))).rejects.toMatchObject({ kind: "down" });
  });
  it("url-encodes ids", async () => {
    const f = fetchOf(json({ status: "pending" }));
    await getReply("a/b", f);
    expect(calls(f)[0]![0]).toBe("/api/reply/a%2Fb");
  });
  it("health is true only for {ok: true}", async () => {
    expect(await health(fetchOf(json({ ok: true })))).toBe(true);
    expect(await health(fetchOf(json({ ok: false })))).toBe(false);
    expect(await health(fetchOf(json({}, 500)))).toBe(false);
    expect(await health(fetchOf(new Error("x")))).toBe(false);
  });
});

describe("waitForReply", () => {
  const pending = () => json({ status: "pending" });
  const done = () => json({ status: "done", text: "Yes.", trace_id: "t1" });
  it("polls until the reply arrives", async () => {
    const f = fetchOf(pending(), pending(), done());
    expect(await waitForReply("id", { f, sleep: noSleep })).toEqual({ text: "Yes.", traceId: "t1" });
    expect(calls(f)).toHaveLength(3);
  });
  it("rides out a few failed polls", async () => {
    const f = fetchOf(new TypeError("blip"), json({}, 502), done());
    expect((await waitForReply("id", { f, sleep: noSleep })).text).toBe("Yes.");
  });
  it("gives up after four failures in a row", async () => {
    const f = fetchOf(new TypeError("down"));
    await expect(waitForReply("id", { f, sleep: noSleep })).rejects.toMatchObject({ kind: "down" });
    expect(calls(f)).toHaveLength(4);
  });
  it("stops at the timeout even while the service keeps saying pending", async () => {
    const f = fetchOf(pending());
    await expect(waitForReply("id", { f, sleep: noSleep, intervalMs: 1000, timeoutMs: 3000 })).rejects.toMatchObject({ kind: "down" });
    expect(calls(f).length).toBe(4);
  });
  it("aborts at once", async () => {
    const c = new AbortController();
    c.abort();
    await expect(waitForReply("id", { f: fetchOf(pending()), sleep: noSleep, signal: c.signal })).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("storage that may be blocked", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("makes a valid session id and keeps it", () => {
    const a = getSession();
    expect(a).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(getSession()).toBe(a);
  });
  it("still works when localStorage throws on every access", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); },
    });
    safeSet("k-test", "v");
    expect(safeGet("k-test")).toBe("v");
    const s = getSession();
    expect(getSession()).toBe(s);
  });
  it("replaces a stored session id that the server would refuse", () => {
    safeSet("onebar-session", "bad id!");
    expect(getSession()).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  });
  it("reads the place out of the server's confirmation and nothing else", () => {
    expect(parsePlaceReply("Place set: Zermatt, Switzerland. Ask your question.")).toBe("Zermatt, Switzerland");
    expect(parsePlaceReply("Place set: 46.500,7.900. Ask your question.")).toBe("46.500,7.900");
    expect(parsePlaceReply("Could not find that place.")).toBeNull();
    expect(parsePlaceReply("Place set: x")).toBeNull();
  });
});

describe("theme", () => {
  it("cycles system, light, dark and back", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });
  it("sets and clears the attribute the tokens listen to", () => {
    const el = document.createElement("div");
    applyTheme("dark", el);
    expect(el.dataset.theme).toBe("dark");
    applyTheme("system", el);
    expect(el.dataset.theme).toBeUndefined();
  });
});

describe("useConversation", () => {
  const example = (examples as unknown as Trace[])[0]!;
  const fakeTrace: Trace = { ...example, recorded: false };
  const deps = (over: Partial<Deps> = {}): Deps => ({
    send: vi.fn(async () => "m1"),
    wait: vi.fn(async () => ({ text: example.reply, traceId: "t1" })),
    trace: vi.fn(async () => fakeTrace),
    session: () => "sess-12345678",
    pause: async () => {},
    lookup: vi.fn(async () => undefined),
    ...over,
  });
  beforeEach(() => localStorage.clear());

  it("shows the question at once, then the reply with its trace marked fresh", async () => {
    const { result } = renderHook(() => useConversation(deps()));
    await act(async () => {
      await result.current.send("  ridge ok by 3:30pm then car?  ");
    });
    const [you, reply] = result.current.messages;
    expect(you).toMatchObject({ role: "you", text: "ridge ok by 3:30pm then car?", status: "done" });
    expect(reply).toMatchObject({ role: "reply", status: "done", text: example.reply, traceId: "t1", fresh: true });
    expect(reply!.trace!.numbers).toHaveLength(3);
    expect(result.current.pending).toBe(false);
  });
  it("ignores an empty message", async () => {
    const d = deps();
    const { result } = renderHook(() => useConversation(d));
    await act(async () => result.current.send("   "));
    expect(result.current.messages).toEqual([]);
    expect(d.send).not.toHaveBeenCalled();
  });
  it("is pending while waiting", async () => {
    let release: (v: { text: string; traceId: string | null }) => void = () => {};
    const d = deps({ wait: vi.fn(() => new Promise((r) => (release = r))) as Deps["wait"] });
    const { result } = renderHook(() => useConversation(d));
    act(() => void result.current.send("storm?"));
    await waitFor(() => expect(result.current.pending).toBe(true));
    await act(async () => release({ text: "No storm.", traceId: null }));
    await waitFor(() => expect(result.current.pending).toBe(false));
  });
  it("keeps the reply when only its trace fails to load", async () => {
    const d = deps({ trace: vi.fn(async () => { throw new ApiError("down"); }) });
    const { result } = renderHook(() => useConversation(d));
    await act(async () => result.current.send("storm?"));
    expect(result.current.messages[1]).toMatchObject({ status: "done", text: example.reply, fresh: false });
    expect(result.current.messages[1]!.trace).toBeUndefined();
  });
  it("turns a service failure into a plain message on the reply line", async () => {
    const d = deps({ send: vi.fn(async () => { throw new ApiError("rate"); }) });
    const { result } = renderHook(() => useConversation(d));
    await act(async () => result.current.send("storm?"));
    expect(result.current.messages[1]).toMatchObject({ status: "error", text: new ApiError("rate").message });
  });
  it("sets the place through the service, remembers it, and reports the server's words", async () => {
    const d = deps({ wait: vi.fn(async () => ({ text: "Place set: Zermatt, Switzerland. Ask your question.", traceId: null })) });
    const { result } = renderHook(() => useConversation(d));
    let out: { ok: boolean; text: string } | undefined;
    await act(async () => { out = await result.current.setPlace("Zermatt"); });
    expect(out).toEqual({ ok: true, text: "Place set: Zermatt, Switzerland. Ask your question." });
    expect(d.send).toHaveBeenCalledWith("sess-12345678", "PLACE Zermatt", expect.any(Function), undefined);
    expect(result.current.place).toBe("Zermatt, Switzerland");
    expect(localStorage.getItem("onebar-place")).toBe("Zermatt, Switzerland");
    expect(result.current.messages[0]).toMatchObject({ role: "note" });
  });
  it("sends what the browser looked up, and remembers the spot the server confirmed", async () => {
    const hint = { place: { query: "Zermatt", name: "Zermatt, Switzerland", lat: 46.02, lon: 7.75 } };
    const d = deps({
      lookup: vi.fn(async () => hint),
      wait: vi.fn(async () => ({ text: "Place set: Zermatt, Switzerland. Ask your question.", traceId: null })),
    });
    const { result } = renderHook(() => useConversation(d));
    await act(async () => { await result.current.setPlace("Zermatt"); });
    expect(d.lookup).toHaveBeenCalledWith("PLACE Zermatt", null);
    expect(d.send).toHaveBeenCalledWith("sess-12345678", "PLACE Zermatt", expect.any(Function), hint);
    expect(JSON.parse(localStorage.getItem("onebar-place-pos")!)).toEqual({ lat: 46.02, lon: 7.75 });
  });
  it("tells the server the place again when it has lost it, keeps the chosen name, and asks once more", async () => {
    localStorage.setItem("onebar-place", "Zermatt, Switzerland");
    localStorage.setItem("onebar-place-pos", JSON.stringify({ lat: 46.02, lon: 7.75 }));
    const replies = [
      { text: "No place yet. Text TRIP <place> BACK 17:00 CONTACT <email> first, then ask.", traceId: null },
      { text: "Place set: 46.020,7.750. Ask your question.", traceId: null },
      { text: example.reply, traceId: "t1" },
    ];
    const d = deps({ wait: vi.fn(async () => replies.shift()!) });
    const { result } = renderHook(() => useConversation(d));
    await act(async () => result.current.send("storm?"));
    const sent = (d.send as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[1]);
    expect(sent).toEqual(["storm?", "PLACE 46.02, 7.75", "storm?"]);
    expect(result.current.messages[1]).toMatchObject({ status: "done", text: example.reply });
    expect(result.current.place).toBe("Zermatt, Switzerland");
  });
  it("passes a lost-place reply through when the page has no spot to restore", async () => {
    const d = deps({ wait: vi.fn(async () => ({ text: "No place yet. Text TRIP first.", traceId: null })) });
    const { result } = renderHook(() => useConversation(d));
    await act(async () => result.current.send("storm?"));
    expect(d.send).toHaveBeenCalledTimes(1);
    expect(result.current.messages[1]).toMatchObject({ status: "done", text: "No place yet. Text TRIP first." });
  });
  it("reports a place the service could not find without remembering it", async () => {
    const d = deps({ wait: vi.fn(async () => ({ text: "Could not find that place. Use PLACE lat,lon, like 46.55,7.98.", traceId: null })) });
    const { result } = renderHook(() => useConversation(d));
    let out: { ok: boolean } | undefined;
    await act(async () => { out = await result.current.setPlace("Nowhereville"); });
    expect(out!.ok).toBe(false);
    expect(result.current.place).toBeNull();
  });
  it("refuses an empty place without calling the service", async () => {
    const d = deps();
    const { result } = renderHook(() => useConversation(d));
    let out: { ok: boolean } | undefined;
    await act(async () => { out = await result.current.setPlace("  "); });
    expect(out!.ok).toBe(false);
    expect(d.send).not.toHaveBeenCalled();
  });
  it("replays a recorded example through the thread and marks it as recorded", async () => {
    const d = deps();
    const { result } = renderHook(() => useConversation(d));
    await act(async () => result.current.replay(example));
    const [you, reply] = result.current.messages;
    expect(you).toMatchObject({ role: "you", recorded: true, text: example.question });
    expect(reply).toMatchObject({ role: "reply", recorded: true, status: "done", fresh: true });
    expect(d.send).not.toHaveBeenCalled(); // nothing went to the service
  });
  it("markSeen stops a reply being treated as new", async () => {
    const { result } = renderHook(() => useConversation(deps()));
    await act(async () => result.current.send("storm?"));
    const id = result.current.messages[1]!.id;
    act(() => result.current.markSeen(id));
    expect(result.current.messages[1]!.fresh).toBe(false);
  });
  it("does not throw or update state after unmount", async () => {
    let release: (v: { text: string; traceId: string | null }) => void = () => {};
    const d = deps({ wait: vi.fn(() => new Promise((r) => (release = r))) as Deps["wait"] });
    const { result, unmount } = renderHook(() => useConversation(d));
    act(() => void result.current.send("storm?"));
    unmount();
    await expect(Promise.resolve().then(() => release({ text: "late", traceId: null }))).resolves.toBeUndefined();
  });
});
