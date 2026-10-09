import { useEffect, useState } from "react";
import type { AuditState } from "../hooks/useAuditSequence";
import type { Conversation } from "../lib/conversation";
import { Composer } from "./Composer";
import styles from "./Handset.module.css";
import { PlacePicker } from "./PlacePicker";
import { SignalMark } from "./SignalMark";
import { Thread } from "./Thread";

interface Props {
  conv: Conversation;
  selectedId: string | null;
  onSelect: (id: string) => void;
  seq: AuditState | null;
  active: number | null;
  onActivate: (i: number | null) => void;
  registerToken: (i: number, el: HTMLElement | null) => void;
  /** The result line for the selected reply. Null while it is still being checked or when nothing is selected. */
  verdict: { text: string; tone: "good" | "bad" } | null;
}

/** The phone side of the product: where you are, the thread, and the box you type in. No drawn device. */
export function Handset({ conv, selectedId, onSelect, seq, active, onActivate, registerToken, verdict }: Props) {
  const [picking, setPicking] = useState(conv.place === null && conv.messages.length === 0);

  // A place that arrives from outside the picker (a PLACE reply) closes it.
  useEffect(() => {
    if (conv.place) setPicking(false);
  }, [conv.place]);

  const empty = conv.messages.length === 0;
  const checking = selectedId !== null && seq !== null && !seq.done;

  return (
    <section className={styles.handset} aria-label="Phone">
      <div className={styles.status}>
        <SignalMark lit={1} size={18} title="One bar of signal" />
        <span className={styles.statusText}>1 bar</span>
        <button
          type="button"
          className={styles.place}
          onClick={() => setPicking((p) => !p)}
          aria-expanded={picking}
        >
          <span className={styles.placeName}>{conv.place ?? "No place set"}</span>
          <span className={styles.placeAction}>
            {conv.place ? "Change" : "Set"}
            <span className="visually-hidden"> place</span>
          </span>
        </button>
      </div>

      {picking ? (
        <PlacePicker current={conv.place} onSubmit={conv.setPlace} onReplay={(ex) => void conv.replay(ex)} onClose={() => setPicking(false)} />
      ) : (
        <>
          {empty ? (
            <div className={styles.empty}>
              <h2>Ask one question</h2>
              <p>{conv.place ? `The forecast for ${conv.place} is read when you send it. Pick an example or type your own.` : "Set a place first, then ask."}</p>
            </div>
          ) : (
            <Thread
              messages={conv.messages}
              selectedId={selectedId}
              onSelect={onSelect}
              seq={seq}
              active={active}
              onActivate={onActivate}
              registerToken={registerToken}
            />
          )}
          <p className={styles.verdict} data-tone={checking ? "muted" : (verdict?.tone ?? "muted")} aria-live="polite">
            {checking ? "Checking the reply" : (verdict?.text ?? "")}
          </p>
          <Composer onSend={(t) => void conv.send(t)} busy={conv.pending} showExamples={empty && conv.place !== null} />
        </>
      )}
    </section>
  );
}
