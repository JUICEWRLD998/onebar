import { m } from "motion/react";
import { useEffect, useRef } from "react";
import type { AuditState } from "../hooks/useAuditSequence";
import { dur, ease, prefersReducedMotion } from "../lib/motion";
import type { Message } from "../lib/types";
import styles from "./Handset.module.css";
import { ReplyBubble } from "./ReplyBubble";

interface Props {
  messages: Message[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  seq: AuditState | null;
  active: number | null;
  onActivate: (i: number | null) => void;
  registerToken: (i: number, el: HTMLElement | null) => void;
}

const enter = { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: dur.short, ease: ease.out } };

export function Thread({ messages, selectedId, onSelect, seq, active, onActivate, registerToken }: Props) {
  const end = useRef<HTMLLIElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [messages.length]);

  return (
    <ol className={styles.thread} aria-label="Messages" aria-busy={messages.some((x) => x.status === "pending")}>
      {messages.map((msg) => {
        if (msg.role === "you")
          return (
            <m.li key={msg.id} className={styles.you} {...enter}>
              {msg.text}
            </m.li>
          );
        if (msg.status === "pending")
          return (
            <m.li key={msg.id} className={msg.role === "note" ? styles.note : styles.waiting} {...enter}>
              <span>{msg.role === "note" ? "Looking up the place" : "Reading the forecast"}</span>
              <span className={styles.dots} aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            </m.li>
          );
        if (msg.status === "error")
          return (
            <m.li key={msg.id} className={styles.error} role="alert" {...enter}>
              <strong>No reply.</strong> {msg.text}
            </m.li>
          );
        if (msg.role === "note")
          return (
            <m.li key={msg.id} className={styles.note} {...enter}>
              {msg.text}
            </m.li>
          );
        return (
          <ReplyBubble
            key={msg.id}
            message={msg}
            selected={msg.id === selectedId}
            seq={msg.id === selectedId ? seq : null}
            active={msg.id === selectedId ? active : null}
            onSelect={() => onSelect(msg.id)}
            onActivate={onActivate}
            registerToken={registerToken}
          />
        );
      })}
      <li ref={end} aria-hidden="true" style={{ height: 0 }} />
    </ol>
  );
}
