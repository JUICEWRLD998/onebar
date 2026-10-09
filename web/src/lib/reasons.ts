import type { NumberTrace, Subject } from "./types";

/** Plain names for the checker's fact keys. The key itself stays visible beside it, for people who want to check. */
export const FACT_LABEL: Record<string, string> = {
  now: "time now",
  temp_now: "temperature now",
  feels_min: "coldest it will feel",
  gust_max: "strongest gust",
  gust_max_at: "time of the strongest gust",
  pop_max: "highest chance of rain",
  storm_first: "first storm hour",
  storm_none: "storm check",
  rain_first: "first rain hour",
  rain_none: "rain check",
  sunset: "sunset",
  sunrise: "sunrise",
  dark_now: "daylight check",
  daylight_left: "daylight left",
  elevation: "elevation",
  car_by: "your car time",
  turn_by: "latest turn-around time",
  turn_now: "turn-around check",
  target: "time you asked about",
  question: "your question",
};

export const factLabel = (key: string) => FACT_LABEL[key] ?? key.replace(/_/g, " ");

/** The topic a group of interchangeable fact keys belongs to, for "leaves out: ..." messages. */
export function topicOf(keys: string[]): string {
  const k = keys[0] ?? "";
  if (k.startsWith("storm")) return "whether a storm is coming";
  if (k === "gust_max") return "the wind gusts";
  if (k.startsWith("rain") || k === "pop_max") return "the chance of rain";
  if (["turn_by", "car_by", "target", "turn_now"].includes(k)) return "the turn-around time";
  if (["sunset", "dark_now", "sunrise"].includes(k)) return "daylight";
  if (["feels_min", "temp_now"].includes(k)) return "the temperature";
  return factLabel(k);
}

export interface Reason {
  kind: "length" | "chars" | "number" | "fact" | "contradiction" | "empty" | "other";
  text: string;
}

/** One checker reason code in words a hiker can read. */
export function reasonText(code: string): Reason {
  const [head = "", ...rest] = code.split(":");
  const detail = rest.join(":");
  switch (head) {
    case "too_long": {
      const n = Number(detail);
      return { kind: "length", text: `${n} characters, ${n - 160} over the 160 limit` };
    }
    case "charset":
      return { kind: "chars", text: `uses characters a basic SMS cannot carry (${detail})` };
    case "invented_number":
      return { kind: "number", text: `${detail} is not in the forecast or your question` };
    case "missing_fact":
      return { kind: "fact", text: `leaves out ${topicOf(detail.split("|"))}` };
    case "contradiction":
      return { kind: "contradiction", text: `says the opposite of the forecast about ${detail === "storm" ? "the storm" : "rain"}` };
    case "empty":
      return { kind: "empty", text: "is empty" };
    default:
      return { kind: "other", text: code };
  }
}

export interface Check {
  id: "length" | "chars" | "numbers" | "facts" | "consistency";
  label: string;
  pass: boolean;
  detail: string;
}

export const SMS_LIMIT = 160;

export function deriveChecks(s: Subject): Check[] {
  const rs = s.reasons.map(reasonText);
  const bad = (k: Reason["kind"]) => rs.filter((r) => r.kind === k);
  const traced = s.numbers.filter((n) => n.ok).length;
  const lengthBad = bad("length")[0];
  const charsBad = bad("chars")[0];
  const numBad = bad("number");
  const factBad = bad("fact");
  const conBad = bad("contradiction");
  return [
    {
      id: "length",
      label: "Under 160 characters",
      pass: !lengthBad,
      detail: lengthBad ? lengthBad.text : `${s.septets} of ${SMS_LIMIT} characters`,
    },
    {
      id: "chars",
      label: "Plain SMS characters",
      pass: !charsBad,
      detail: charsBad ? charsBad.text : "nothing that needs a smartphone to display",
    },
    {
      id: "numbers",
      label: "Every number traced",
      pass: numBad.length === 0 && traced === s.numbers.length,
      detail:
        s.numbers.length === 0
          ? "no numbers to trace"
          : numBad.length || traced !== s.numbers.length
            ? `${traced} of ${s.numbers.length} traced; ${numBad.map((r) => r.text).join("; ") || "one has no source"}`
            : `${traced} of ${s.numbers.length} traced to the forecast or your question`,
    },
    {
      id: "facts",
      label: "Says what the question needs",
      pass: factBad.length === 0,
      detail: factBad.length ? factBad.map((r) => r.text).join("; ") : "the facts this kind of question needs are all there",
    },
    {
      id: "consistency",
      label: "Agrees with the forecast",
      pass: conBad.length === 0,
      detail: conBad.length ? conBad.map((r) => r.text).join("; ") : "no storm or rain claim that the data contradicts",
    },
  ];
}

/** The one-line result under a reply. Same words whether it is shown at once or after the audit plays. */
export function verdict(s: Subject): string {
  const checks = deriveChecks(s);
  const failed = checks.filter((c) => !c.pass).length;
  if (failed === 0) {
    const n = s.numbers.length;
    const traced = n === 0 ? "No numbers to trace." : `${n} of ${n} numbers traced to the forecast.`;
    return `Checked. ${traced} ${s.septets} of ${SMS_LIMIT} characters.`;
  }
  return `Not sent. ${failed} ${failed === 1 ? "check" : "checks"} failed.`;
}

export interface Source {
  key: string;
  label: string;
  hour: string | null; // ISO hour on the place's clock
  fromQuestion: boolean;
}

/** Where a number came from, for its row in the table. Prefers a forecast fact over the question. */
export function sourceOf(n: NumberTrace): Source {
  const fact = n.sources.find(([k]) => k !== "question");
  if (fact) return { key: fact[0], label: factLabel(fact[0]), hour: fact[1], fromQuestion: n.sources.some(([k]) => k === "question") };
  if (n.sources.length) return { key: "question", label: "your question", hour: null, fromQuestion: true };
  return { key: "", label: "no source", hour: null, fromQuestion: false };
}

export const hourLabel = (iso: string | null) => (iso ? iso.slice(11, 16) : "");
