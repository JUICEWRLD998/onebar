import type { AuditState } from "../../hooks/useAuditSequence";
import { hourLabel, sourceOf } from "../../lib/reasons";
import type { NumberTrace } from "../../lib/types";
import styles from "./Audit.module.css";

interface Props {
  numbers: NumberTrace[];
  seq: AuditState;
  active: number | null;
  onActivate: (i: number | null) => void;
  registerRow: (i: number, el: HTMLElement | null) => void;
}

/** One row per number in the reply: the number, the forecast fact it was read from, and the hour that fact is about. */
export function NumberRows({ numbers, seq, active, onActivate, registerRow }: Props) {
  return (
    <section className={styles.numbers} aria-labelledby="numbers-title">
      <h3 id="numbers-title" className={styles.h3}>
        Where each number came from
      </h3>
      {numbers.length === 0 ? (
        <p className={styles.quiet}>This reply has no numbers, so there is nothing to trace.</p>
      ) : (
        <ul className={styles.rows}>
          {numbers.map((n, i) => {
            const src = sourceOf(n);
            const checked = seq.verified > i;
            const state = !n.ok ? "bad" : checked ? "ok" : "pending";
            return (
              <li
                key={`${n.text}-${i}`}
                className={styles.row}
                ref={(el) => registerRow(i, el)}
                data-state={state}
                data-active={active === i && (checked || !n.ok)}
                onPointerEnter={() => onActivate(i)}
                onPointerLeave={() => onActivate(null)}
              >
                <span className={styles.rowNum}>{n.text}</span>
                {n.ok ? (
                  <span className={styles.rowSrc}>
                    {src.label}
                    {src.key && src.key !== "question" && <code className={styles.key}>{src.key}</code>}
                    {src.fromQuestion && src.key !== "question" && <span className={styles.also}> and your question</span>}
                  </span>
                ) : (
                  <span className={styles.rowSrc}>Not in the forecast or your question</span>
                )}
                <span className={styles.rowAt}>{src.hour ? `at ${hourLabel(src.hour)}` : ""}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
