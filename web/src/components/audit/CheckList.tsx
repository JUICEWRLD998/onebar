import type { AuditState } from "../../hooks/useAuditSequence";
import { SMS_LIMIT, deriveChecks } from "../../lib/reasons";
import type { Subject } from "../../lib/types";
import styles from "./Audit.module.css";

interface Props {
  subject: Subject;
  seq: AuditState;
}

/** The length meter and the five checks, ticking in the order the checker runs them. */
export function CheckList({ subject, seq }: Props) {
  const checks = deriveChecks(subject);
  const over = subject.septets > SMS_LIMIT;
  const fill = Math.min(1, subject.septets / SMS_LIMIT) * seq.meter;

  return (
    <section className={styles.checks} aria-labelledby="checks-title">
      <h3 id="checks-title" className={styles.h3}>
        What the checker looked at
      </h3>

      <div className={styles.meterRow}>
        <div className={styles.meter} role="img" aria-label={`${subject.septets} of ${SMS_LIMIT} characters`} data-over={over}>
          <span className={styles.meterFill} style={{ transform: `scaleX(${fill})` }} />
        </div>
        <span className={styles.meterText} data-over={over}>
          {subject.septets} of {SMS_LIMIT}
        </span>
      </div>

      <ul className={styles.checkList}>
        {checks.map((c, i) => {
          const ticked = seq.ticks > i;
          return (
            <li key={c.id} className={styles.check} data-ticked={ticked} data-pass={c.pass}>
              <span className={styles.mark} aria-hidden="true">
                {ticked && (
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" focusable="false">
                    <path d={c.pass ? "M2.5 6.5l2.5 2.5 4.5-5.5" : "M3 3l6 6M9 3l-6 6"} />
                  </svg>
                )}
              </span>
              <span className={styles.checkBody}>
                <span className={styles.checkLabel}>
                  {c.label}
                  <span className="visually-hidden">{ticked ? (c.pass ? ": passed" : ": failed") : ": not checked yet"}</span>
                </span>
                <span className={styles.checkDetail}>{ticked || !c.pass ? c.detail : " "}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
