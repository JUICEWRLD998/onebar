import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AuditSheet } from "../components/audit/AuditSheet";
import { recordedTrace } from "../data/recorded";
import { finalState } from "../hooks/useAuditSequence";
import { getTrace } from "../lib/api";
import type { Model } from "../lib/subject";
import { tokenize } from "../lib/tokenize";
import type { Trace } from "../lib/types";
import styles from "./Page.module.css";

type Load = { status: "loading" } | { status: "ready"; trace: Trace } | { status: "missing" } | { status: "down" };

export function TracePage() {
  const { id = "" } = useParams();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [model, setModel] = useState<Model>("tuned");
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    document.title = "Reply check | OneBar";
    const rec = recordedTrace(id);
    if (rec) {
      setLoad({ status: "ready", trace: rec });
      return;
    }
    const ac = new AbortController();
    setLoad({ status: "loading" });
    getTrace(id, fetch, ac.signal)
      .then((trace) => setLoad({ status: "ready", trace }))
      .catch((e: Error & { kind?: string }) => {
        if (e.name === "AbortError") return;
        setLoad({ status: e.kind === "bad" ? "missing" : "down" });
      });
    return () => ac.abort();
  }, [id]);

  if (load.status !== "ready")
    return (
      <div className={styles.page}>
        <h1 className={styles.h1}>
          {load.status === "loading" ? "Loading the check" : load.status === "missing" ? "No check found" : "The check could not be loaded"}
        </h1>
        <p className={styles.lede}>
          {load.status === "loading"
            ? "Fetching the record of this reply."
            : load.status === "missing"
              ? "This address does not match a reply. Checks are kept for a limited time."
              : "OneBar could not be reached. Try again in a moment."}
        </p>
        <p>
          <Link to="/">Ask a question</Link>
        </p>
      </div>
    );

  const trace = load.trace;
  const segs = tokenize(trace.reply, trace.numbers);
  const seq = finalState(model === "base" && trace.baseline ? trace.baseline.numbers.length : trace.numbers.length, 5);

  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <h1 className={styles.h1}>A checked reply</h1>
        <p className={styles.lede}>
          Question: <q>{trace.question}</q>
        </p>
        <p className={styles.reply}>
          {segs.map((s, k) =>
            s.kind === "text" ? (
              <span key={k}>{s.text}</span>
            ) : (
              <span key={k} className={styles.num} data-ok={s.ok} data-active={active === s.index}>
                {s.text}
              </span>
            ),
          )}
        </p>
      </div>
      <AuditSheet
        trace={trace}
        model={model}
        onModel={setModel}
        seq={seq}
        active={active ?? seq.active}
        onActivate={setActive}
        registerRow={() => {}}
      />
    </div>
  );
}
