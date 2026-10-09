import { m } from "motion/react";
import type { AuditState } from "../hooks/useAuditSequence";
import { dur, ease } from "../lib/motion";
import { sourceOf } from "../lib/reasons";
import { tokenize } from "../lib/tokenize";
import type { Message } from "../lib/types";
import styles from "./Handset.module.css";

interface Props {
  message: Message;
  selected: boolean;
  seq: AuditState | null;
  active: number | null;
  onSelect: () => void;
  onActivate: (i: number | null) => void;
  registerToken: (i: number, el: HTMLElement | null) => void;
}

/**
 * One reply. Its numbers are the thing being judged, so each is a control: a dashed underline until the checker has
 * traced it, a solid accent underline after, a wavy red one if it could not be traced.
 */
export function ReplyBubble({ message, selected, seq, active, onSelect, onActivate, registerToken }: Props) {
  const trace = message.trace;
  const segments = trace ? tokenize(message.text, trace.numbers) : [{ kind: "text" as const, text: message.text }];

  return (
    <m.li
      className={styles.replyItem}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: dur.short, ease: ease.out }}
    >
      <div className={styles.reply} data-selected={selected}>
        {segments.map((seg, k) => {
          if (seg.kind === "text") {
            // Punctuation that follows a number is drawn with it (see `glue` below), so it never wraps onto its own line.
            const prev = segments[k - 1];
            const lead = prev?.kind === "num" ? (/^[.,;:!?)]+/.exec(seg.text)?.[0] ?? "") : "";
            return lead === seg.text ? null : <span key={k}>{seg.text.slice(lead.length)}</span>;
          }
          const next = segments[k + 1];
          const trail = next?.kind === "text" ? (/^[.,;:!?)]+/.exec(next.text)?.[0] ?? "") : "";
          const glue = (node: React.ReactNode) =>
            trail ? (
              <span key={k} className={styles.glue}>
                {node}
                {trail}
              </span>
            ) : (
              node
            );
          const verified = !selected || !seq || seq.verified > seg.index;
          const state = !seg.ok ? "bad" : selected && active === seg.index && verified ? "active" : verified ? "verified" : "pending";
          if (!selected)
            return glue(
              <span key={k} className={styles.token} data-state={state}>
                {seg.text}
              </span>,
            );
          const n = trace!.numbers[seg.index]!;
          return glue(
            <button
              key={k}
              type="button"
              className={styles.token}
              data-state={state}
              ref={(el) => registerToken(seg.index, el)}
              aria-pressed={active === seg.index}
              aria-label={`${seg.text}, ${sourceOf(n).label}. Show where it came from.`}
              onPointerEnter={() => onActivate(seg.index)}
              onPointerLeave={() => onActivate(null)}
              onFocus={() => onActivate(seg.index)}
              onBlur={() => onActivate(null)}
              onClick={() => onActivate(seg.index)}
            >
              {seg.text}
            </button>,
          );
        })}
      </div>
      {message.recorded && <p className={styles.recorded}>Recorded example from the test set. Not live.</p>}
      {trace && !selected && (
        <button type="button" className={styles.again} onClick={onSelect}>
          Show how this was checked
        </button>
      )}
    </m.li>
  );
}
