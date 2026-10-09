import { describe, expect, it } from "vitest";
import examples from "../data/examples.json";
import { deriveChecks, hourLabel, reasonText, sourceOf, topicOf, verdict } from "./reasons";
import { tokenize } from "./tokenize";
import type { NumberTrace, Subject, Trace } from "./types";

const traces = examples as unknown as Trace[];
const num = (text: string, ok = true, sources: NumberTrace["sources"] = [["gust_max", "2026-08-19T00:00"]]): NumberTrace => ({ text, ok, sources });

describe("tokenize", () => {
  it("marks every traced number in a real reply, in order, and loses no text", () => {
    for (const t of traces) {
      const segs = tokenize(t.reply, t.numbers);
      expect(segs.map((s) => s.text).join("")).toBe(t.reply);
      const marked = segs.filter((s) => s.kind === "num");
      expect(marked.map((s) => s.text)).toEqual(t.numbers.map((n) => n.text));
      expect(marked.map((s) => (s.kind === "num" ? s.index : -1))).toEqual(t.numbers.map((_, i) => i));
    }
  });
  it("finds a repeated number at its second occurrence", () => {
    const segs = tokenize("At 14:00 and again 14:00.", [num("14:00"), num("14:00")]);
    expect(segs.filter((s) => s.kind === "num")).toHaveLength(2);
    expect(segs.map((s) => s.text).join("")).toBe("At 14:00 and again 14:00.");
  });
  it("never marks part of a longer number", () => {
    const segs = tokenize("Turn back by 115:30, or at 15:30.", [num("15:30")]);
    const m = segs.find((s) => s.kind === "num")!;
    expect(m.text).toBe("15:30");
    expect(segs.map((s) => s.text).join("")).toBe("Turn back by 115:30, or at 15:30.");
    expect(segs[0]!.text).toBe("Turn back by 115:30, or at "); // the marked one is the second occurrence
  });
  it("leaves a number the text no longer contains unmarked, without throwing", () => {
    expect(tokenize("No storm.", [num("21:00")])).toEqual([{ kind: "text", text: "No storm." }]);
  });
  it("handles an empty reply and no numbers", () => {
    expect(tokenize("", [])).toEqual([]);
    expect(tokenize("No storm.", [])).toEqual([{ kind: "text", text: "No storm." }]);
  });
  it("keeps the ok flag so an invented number can be drawn differently", () => {
    const m = tokenize("Gusts 999km/h.", [num("999km/h", false, [])]).find((s) => s.kind === "num")!;
    expect(m.kind === "num" && m.ok).toBe(false);
  });
});

describe("reasonText", () => {
  it.each([
    ["too_long:241", "length", "241 characters, 81 over the 160 limit"],
    ["charset:❄", "chars", "uses characters a basic SMS cannot carry (❄)"],
    ["invented_number:99%", "number", "99% is not in the forecast or your question"],
    ["missing_fact:storm_first|storm_none", "fact", "leaves out whether a storm is coming"],
    ["missing_fact:gust_max", "fact", "leaves out the wind gusts"],
    ["missing_fact:turn_by|car_by|sunset", "fact", "leaves out the turn-around time"],
    ["contradiction:storm", "contradiction", "says the opposite of the forecast about the storm"],
    ["contradiction:rain", "contradiction", "says the opposite of the forecast about rain"],
    ["empty", "empty", "is empty"],
    ["something_new:x", "other", "something_new:x"],
  ])("%s", (code, kind, text) => {
    expect(reasonText(code)).toEqual({ kind, text });
  });
  it("names a topic for every fact group the checker can demand", () => {
    for (const keys of [["storm_first", "storm_none"], ["gust_max"], ["rain_first", "rain_none", "pop_max"], ["sunset", "dark_now"],
      ["feels_min", "temp_now"], ["turn_by", "car_by", "target", "turn_now", "sunset"]]) {
      expect(topicOf(keys)).not.toMatch(/_/);
    }
  });
});

const subject = (over: Partial<Subject> = {}): Subject => ({
  text: "x", septets: 65, numbers: [num("15:30"), num("21:00"), num("54km/h")], reasons: [], passed: true, ...over,
});

describe("checks and verdict", () => {
  it("passes all five checks for a clean reply and says so in plain words", () => {
    const checks = deriveChecks(subject());
    expect(checks.map((c) => c.id)).toEqual(["length", "chars", "numbers", "facts", "consistency"]);
    expect(checks.every((c) => c.pass)).toBe(true);
    expect(verdict(subject())).toBe("Checked. 3 of 3 numbers traced to the forecast. 65 of 160 characters.");
  });
  it("matches the recorded verdict wording used in the design", () => {
    for (const t of traces) {
      const v = verdict({ text: t.reply, septets: t.septets, numbers: t.numbers, reasons: [], passed: true });
      expect(v).toBe(`Checked. ${t.numbers.length} of ${t.numbers.length} numbers traced to the forecast. ${t.septets} of 160 characters.`);
    }
  });
  it("says what failed for the base model's real draft on the ridge question", () => {
    const b = traces[0]!.baseline!;
    const s = { text: b.text, septets: b.septets, numbers: b.numbers, reasons: b.reasons, passed: b.passed };
    const checks = deriveChecks(s);
    expect(checks.filter((c) => !c.pass).map((c) => c.id)).toEqual(["length", "consistency"]);
    expect(checks[0]!.detail).toBe("241 characters, 81 over the 160 limit");
    expect(verdict(s)).toBe("Not sent. 2 checks failed.");
  });
  it("singular wording for one failure", () => {
    expect(verdict(subject({ reasons: ["missing_fact:gust_max"] }))).toBe("Not sent. 1 check failed.");
  });
  it("flags an untraced number even when no reason code names it", () => {
    const c = deriveChecks(subject({ numbers: [num("1", true), num("999", false, [])] })).find((x) => x.id === "numbers")!;
    expect(c.pass).toBe(false);
    expect(c.detail).toContain("1 of 2 traced");
  });
  it("copes with a reply that has no numbers", () => {
    const s = subject({ numbers: [], septets: 10 });
    expect(deriveChecks(s).find((c) => c.id === "numbers")!.pass).toBe(true);
    expect(verdict(s)).toBe("Checked. No numbers to trace. 10 of 160 characters.");
  });
});

describe("sourceOf", () => {
  it("prefers a forecast fact and keeps its hour", () => {
    expect(sourceOf(num("21:00", true, [["storm_first", "2026-08-19T21:00"]]))).toEqual({
      key: "storm_first", label: "first storm hour", hour: "2026-08-19T21:00", fromQuestion: false,
    });
  });
  it("reports a time the hiker wrote as a target that is also in the question", () => {
    expect(sourceOf(num("15:30", true, [["target", null], ["question", null]]))).toMatchObject({ key: "target", fromQuestion: true, hour: null });
  });
  it("falls back to the question, then to no source", () => {
    expect(sourceOf(num("3", true, [["question", null]])).label).toBe("your question");
    expect(sourceOf(num("9", false, [])).label).toBe("no source");
  });
  it("formats an hour for display", () => {
    expect(hourLabel("2026-08-19T21:00")).toBe("21:00");
    expect(hourLabel(null)).toBe("");
  });
});
