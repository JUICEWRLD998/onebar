import { useEffect, useRef, useState, type FormEvent } from "react";
import { QUICK_PLACES, recordedExamples } from "../data/recorded";
import { placeProblem } from "../lib/format";
import type { Trace } from "../lib/types";
import styles from "./Handset.module.css";

interface Props {
  /** The place already set, if any: the picker then offers a way back. */
  current: string | null;
  onSubmit: (name: string) => Promise<{ ok: boolean; text: string }>;
  onReplay: (example: Trace) => void;
  onClose: () => void;
}

export function PlacePicker({ current, onSubmit, onReplay, onClose }: Props) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    input.current?.focus({ preventScroll: true });
  }, []);

  async function choose(value: string) {
    const v = value.trim();
    if (!v || busy) return;
    setBusy(true);
    setProblem(null);
    const res = await onSubmit(v);
    setBusy(false);
    if (res.ok) onClose();
    else setProblem(placeProblem(res.text) || "Could not set the place. Check your connection and try again.");
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void choose(name);
  }

  return (
    <section className={styles.picker} aria-labelledby="picker-title">
      <h2 id="picker-title">{current ? "Change your place" : "Where are you?"}</h2>
      <p className={styles.pickerHint}>
        The forecast and the terrain are read for this place. A town, a peak, or coordinates like 46.55, 7.98.
      </p>

      <form className={styles.pickerGroup} onSubmit={submit}>
        <label className={styles.pickerLabel} htmlFor="place-input">
          Place name
        </label>
        <div className={styles.row}>
          <input
            id="place-input"
            ref={input}
            className={styles.input}
            type="text"
            autoComplete="off"
            spellCheck={false}
            maxLength={80}
            placeholder="Zermatt"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-describedby={problem ? "place-problem" : undefined}
            aria-invalid={problem ? true : undefined}
          />
          <button type="submit" className={styles.send} disabled={busy || !name.trim()}>
            {busy ? "Looking up" : "Set place"}
          </button>
        </div>
        {problem && (
          <p id="place-problem" className={styles.problem} role="alert">
            {problem}
          </p>
        )}
      </form>

      <div className={styles.pickerGroup}>
        <span className={styles.pickerLabel} id="quick-label">
          Or pick one
        </span>
        <div className={styles.chips} role="group" aria-labelledby="quick-label">
          {QUICK_PLACES.map((p) => (
            <button key={p} type="button" className={styles.chip} disabled={busy} onClick={() => void choose(p)}>
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.pickerGroup}>
        <span className={styles.pickerLabel} id="replay-label">
          Or watch a recorded example, no place needed
        </span>
        <ul className={styles.replays} aria-labelledby="replay-label">
          {recordedExamples.map((ex) => (
            <li key={ex.id}>
              <button
                type="button"
                className={styles.replay}
                onClick={() => {
                  onReplay(ex);
                  onClose();
                }}
              >
                {ex.question}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {current && (
        <button type="button" className={styles.close} onClick={onClose}>
          Keep {current}
        </button>
      )}
    </section>
  );
}
