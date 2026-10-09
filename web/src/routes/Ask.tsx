import { useCallback, useEffect, useRef, useState } from "react";
import { AuditSheet } from "../components/audit/AuditSheet";
import { Handset } from "../components/Handset";
import { Leader } from "../components/Leader";
import { recordedExamples } from "../data/recorded";
import { useAuditSequence } from "../hooks/useAuditSequence";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useConversation } from "../lib/conversation";
import { verdict } from "../lib/reasons";
import { subjectOf, type Model } from "../lib/subject";
import styles from "./Ask.module.css";

export function Ask() {
  const conv = useConversation();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [model, setModel] = useState<Model>("tuned");
  const [hot, setHot] = useState<number | null>(null);
  const [container, setContainer] = useState<HTMLElement | null>(null);
  const [leftEl, setLeftEl] = useState<HTMLElement | null>(null);
  const [sheetEl, setSheetEl] = useState<HTMLElement | null>(null);
  const tokens = useRef(new Map<number, HTMLElement>());
  const rows = useRef(new Map<number, HTMLElement>());
  const wide = useMediaQuery("(min-width: 64rem)");

  useEffect(() => {
    document.title = "Ask | OneBar";
  }, []);

  // The newest reply that has a trace is the one on the sheet.
  const latest = [...conv.messages].reverse().find((x) => x.role === "reply" && x.status === "done" && x.trace);
  useEffect(() => {
    if (latest && latest.id !== selectedId) {
      setSelectedId(latest.id);
      setModel("tuned");
      setHot(null);
    }
  }, [latest?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const selected = conv.messages.find((x) => x.id === selectedId && x.trace) ?? null;
  const sample = selected === null;
  const raw = selected?.trace ?? recordedExamples[0]!;
  // A live trace carries coordinates only; the name the hiker set is what the map should call the place.
  const trace = !selected || raw.place?.name || !raw.place || !conv.place ? raw : { ...raw, place: { ...raw.place, name: conv.place } };

  const seq = useAuditSequence({
    id: selected?.id ?? "sample",
    play: Boolean(selected?.fresh),
    numbers: trace.numbers.length,
    onDone: selected ? () => conv.markSeen(selected.id) : undefined,
  });

  const active = hot ?? seq.active;
  const tuned = model === "tuned" || trace.baseline === null;
  const line = selected && seq.done ? verdict(subjectOf(trace, "tuned")) : null;

  const registerToken = useCallback((i: number, el: HTMLElement | null) => {
    if (el) tokens.current.set(i, el);
    else tokens.current.delete(i);
  }, []);
  const registerRow = useCallback((i: number, el: HTMLElement | null) => {
    if (el) rows.current.set(i, el);
    else rows.current.delete(i);
  }, []);

  const clip = leftEl?.querySelector<HTMLElement>('ol[aria-label="Messages"]') ?? null;

  return (
    <div className={styles.page}>
      <div className={styles.intro}>
        <h1 className={styles.h1}>Ask about the weather on your route</h1>
        <p className={styles.lede}>
          One question, one 160-character reply. Every number in it is traced to the forecast, and you can see where.
        </p>
      </div>

      <div className={styles.stage} ref={setContainer}>
        <div className={styles.left} ref={setLeftEl}>
          <Handset
            conv={conv}
            selectedId={selected?.id ?? null}
            onSelect={(id) => {
              setSelectedId(id);
              setModel("tuned");
            }}
            seq={selected ? seq : null}
            active={selected ? active : null}
            onActivate={setHot}
            registerToken={registerToken}
            verdict={line ? { text: line, tone: "good" } : null}
          />
        </div>
        <div className={styles.right}>
          <AuditSheet
            trace={trace}
            traceId={selected?.traceId}
            sample={sample}
            model={tuned ? "tuned" : "base"}
            onModel={setModel}
            seq={seq}
            active={active}
            onActivate={setHot}
            registerRow={registerRow}
            sheetRef={setSheetEl}
          />
        </div>
        {wide && !sample && tuned && active !== null && (
          <Leader
            container={container}
            token={tokens.current.get(active) ?? null}
            row={rows.current.get(active) ?? null}
            clip={clip}
            left={leftEl}
            right={sheetEl}
            drawKey={`${selected?.id}:${active}`}
          />
        )}
      </div>
    </div>
  );
}
