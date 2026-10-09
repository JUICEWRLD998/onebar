import type { Model } from "../../lib/subject";
import styles from "./Audit.module.css";

interface Props {
  model: Model;
  onChange: (m: Model) => void;
  /** The base model's draft exists for this reply. */
  hasBase: boolean;
}

export function ModelToggle({ model, onChange, hasBase }: Props) {
  return (
    <div className={styles.toggle} role="group" aria-label="Which model wrote the reply">
      <button type="button" className={styles.toggleBtn} aria-pressed={model === "tuned"} onClick={() => onChange("tuned")}>
        Tuned model
      </button>
      <button
        type="button"
        className={styles.toggleBtn}
        aria-pressed={model === "base"}
        disabled={!hasBase}
        title={hasBase ? undefined : "No base-model draft was recorded for this reply"}
        onClick={() => onChange("base")}
      >
        Base model
      </button>
    </div>
  );
}
