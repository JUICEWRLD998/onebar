import { Link } from "react-router-dom";
import type { AuditState } from "../../hooks/useAuditSequence";
import { finalState } from "../../hooks/useAuditSequence";
import { useContours } from "../../hooks/useContours";
import { pathText } from "../../lib/format";
import { verdict } from "../../lib/reasons";
import { subjectOf, type Model } from "../../lib/subject";
import { tokenize } from "../../lib/tokenize";
import type { Trace } from "../../lib/types";
import { AuditMap } from "./AuditMap";
import styles from "./Audit.module.css";
import { CheckList } from "./CheckList";
import { HourStrip } from "./HourStrip";
import { ModelToggle } from "./ModelToggle";
import { NumberRows } from "./NumberRows";

interface Props {
  trace: Trace;
  /** Set when the trace has its own page. */
  traceId?: string;
  /** A recorded example shown before the visitor has asked anything. */
  sample?: boolean;
  model: Model;
  onModel: (m: Model) => void;
  seq: AuditState;
  active: number | null;
  onActivate: (i: number | null) => void;
  registerRow: (i: number, el: HTMLElement | null) => void;
  /** Called with the sheet element so the leader line knows where the margin is. */
  sheetRef?: (el: HTMLElement | null) => void;
}

/** The whole proof for one reply, as one sheet: where, when, which numbers came from where, which checks passed. */
export function AuditSheet({ trace, traceId, sample, model, onModel, seq, active, onActivate, registerRow, sheetRef }: Props) {
  const { contours, status } = useContours(trace);
  const base = model === "base" && trace.baseline !== null;
  const subject = subjectOf(trace, base ? "base" : "tuned");
  // The base model's draft was never played through the sequence: it shows its end state.
  const shownSeq = base ? finalState(subject.numbers.length, 5) : seq;
  const shownActive = base ? (subject.numbers.length > 0 ? active : null) : active;
  const activeNumber = shownActive === null ? undefined : subject.numbers[shownActive];
  const activeHour = activeNumber ? (activeNumber.sources.find(([k]) => k !== "question")?.[1] ?? null) : null;

  return (
    <article className={styles.sheet} ref={sheetRef} aria-labelledby="sheet-title">
      <header className={styles.head}>
        <div className={styles.headText}>
          <h2 id="sheet-title" className={styles.title}>
            {sample ? "A recorded example, checked" : "How this reply was checked"}
          </h2>
          <p className={styles.caption}>
            {sample
              ? `“${trace.question}” in ${trace.place?.name ?? "a recorded place"}. Ask your own question and its proof replaces this.`
              : base
                ? "The same question, answered by the base model. It was not sent."
                : pathText(trace.path)}
          </p>
        </div>
        <ModelToggle model={base ? "base" : "tuned"} onChange={onModel} hasBase={trace.baseline !== null} />
      </header>

      {base && (
        <div className={styles.draft}>
          <p className={styles.draftLabel}>Base model draft</p>
          <p className={styles.draftText}>
            {tokenize(subject.text, subject.numbers).map((seg, k) =>
              seg.kind === "text" ? (
                <span key={k}>{seg.text}</span>
              ) : (
                <span key={k} className={styles.draftNum} data-ok={seg.ok} data-active={shownActive === seg.index}>
                  {seg.text}
                </span>
              ),
            )}
          </p>
          <p className={styles.draftVerdict} data-tone={subject.passed ? "good" : "bad"}>
            {verdict(subject)}
          </p>
        </div>
      )}

      <AuditMap trace={trace} contours={contours} status={status} />
      <HourStrip hours={trace.hours} activeHour={activeHour} />
      <NumberRows numbers={subject.numbers} seq={shownSeq} active={shownActive} onActivate={onActivate} registerRow={registerRow} />
      <CheckList subject={subject} seq={shownSeq} />

      <footer className={styles.foot}>
        <p className={styles.footVerdict} data-tone={subject.passed ? "good" : "bad"}>
          {verdict(subject)}
        </p>
        {traceId && !sample && (
          <Link className={styles.permalink} to={`/trace/${encodeURIComponent(traceId)}`}>
            Open this check on its own page
          </Link>
        )}
      </footer>
    </article>
  );
}
