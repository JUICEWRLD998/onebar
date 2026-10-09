import type { NumberTrace } from "./types";

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "num"; text: string; index: number; ok: boolean };

const isDigit = (c: string | undefined) => c !== undefined && c >= "0" && c <= "9";

/**
 * Split a reply into plain text and the numbers the checker traced, in order. `numbers` comes from the trace in
 * the order the checker found them, so each is looked up after the previous one. A match glued to other digits
 * ("115:30" when looking for "15:30") is skipped, never half-marked.
 */
export function tokenize(reply: string, numbers: NumberTrace[]): Segment[] {
  const out: Segment[] = [];
  let cursor = 0;
  numbers.forEach((n, index) => {
    let at = reply.indexOf(n.text, cursor);
    while (at !== -1 && (isDigit(reply[at - 1]) || isDigit(reply[at + n.text.length]))) {
      at = reply.indexOf(n.text, at + 1);
    }
    if (at === -1) return; // the checker saw it, the text no longer contains it: leave it unmarked
    if (at > cursor) out.push({ kind: "text", text: reply.slice(cursor, at) });
    out.push({ kind: "num", text: n.text, index, ok: n.ok });
    cursor = at + n.text.length;
  });
  if (cursor < reply.length) out.push({ kind: "text", text: reply.slice(cursor) });
  return out;
}
