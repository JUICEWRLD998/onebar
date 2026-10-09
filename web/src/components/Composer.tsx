import { useState, type FormEvent } from "react";
import { EXAMPLE_QUESTIONS } from "../data/recorded";
import styles from "./Handset.module.css";

export const MAX_CHARS = 500;

interface Props {
  onSend: (text: string) => void;
  /** A reply is on its way: wait for it, so the thread stays in order. */
  busy: boolean;
  /** Show the example questions (an empty thread). */
  showExamples: boolean;
}

export function Composer({ onSend, busy, showExamples }: Props) {
  const [text, setText] = useState("");
  const trimmed = text.trim();
  const canSend = trimmed.length > 0 && !busy;

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSend) return;
    onSend(trimmed);
    setText("");
  }

  return (
    <form className={styles.composer} onSubmit={submit} aria-label="Ask a question">
      {showExamples && (
        <div className={styles.chips} role="group" aria-label="Example questions">
          {EXAMPLE_QUESTIONS.map((q) => (
            <button key={q} type="button" className={styles.chip} disabled={busy} onClick={() => onSend(q)}>
              {q}
            </button>
          ))}
        </div>
      )}
      <div className={styles.row}>
        <label className="visually-hidden" htmlFor="ask-input">
          Your question
        </label>
        <input
          id="ask-input"
          className={styles.input}
          type="text"
          inputMode="text"
          enterKeyHint="send"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={MAX_CHARS}
          placeholder="storm before 3?"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" className={styles.send} disabled={!canSend}>
          Send
        </button>
      </div>
      {text.length > MAX_CHARS - 80 && (
        <span className={styles.count} data-near={text.length >= MAX_CHARS} aria-live="polite">
          {text.length} of {MAX_CHARS}
        </span>
      )}
    </form>
  );
}
