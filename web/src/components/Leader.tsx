import { m } from "motion/react";
import { useLayoutEffect, useState } from "react";
import { leaderPath } from "../lib/elbow";
import { dur, ease } from "../lib/motion";
import styles from "./Leader.module.css";

interface Props {
  /** The positioned element that holds both columns. The overlay fills it. */
  container: HTMLElement | null;
  /** The number in the reply that is in focus, and the row in the audit sheet it is read from. */
  token: HTMLElement | null;
  row: HTMLElement | null;
  /** The scrolling thread: a number scrolled out of it has no line. */
  clip: HTMLElement | null;
  /** The two columns, to find the gutter between them. */
  left: HTMLElement | null;
  right: HTMLElement | null;
  /** Changes when a new line should draw itself. */
  drawKey: string;
}

/**
 * One map-style callout at a time: from the number being checked, down under its line, across the gutter, along it to
 * the row's height and into the row. It reads the layout after every render, so it follows scrolling and resizing.
 */
export function Leader({ container, token, row, clip, left, right, drawKey }: Props) {
  const [geo, setGeo] = useState<{ d: string; end: { x: number; y: number }; w: number; h: number } | null>(null);

  useLayoutEffect(() => {
    let next: typeof geo = null;
    if (container && token && row && left && right && token.isConnected && row.isConnected) {
      const c = container.getBoundingClientRect();
      const t = token.getBoundingClientRect();
      const r = row.getBoundingClientRect();
      const a = left.getBoundingClientRect();
      const b = right.getBoundingClientRect();
      const k = clip?.getBoundingClientRect();
      const visible = !k || (t.top >= k.top - 1 && t.bottom <= k.bottom + 1);
      if (visible && t.width > 0 && r.width > 0) {
        // The token's box is as tall as its line (line-height), so anchor to the text itself: start just under the
        // underline and run in the gap between this line and the next, about 0.9em below the text's middle.
        const fs = Number.parseFloat(getComputedStyle(token).fontSize) || 17;
        const cy = t.top + t.height / 2 - c.top;
        const start = { x: t.left + t.width / 2 - c.left, y: cy + 0.55 * fs };
        const end = { x: r.left - c.left, y: r.top + r.height / 2 - c.top };
        const gutterX = (a.right + b.left) / 2 - c.left;
        next = { d: leaderPath(start, end, gutterX, cy + 0.9 * fs), end, w: c.width, h: c.height };
      }
    }
    setGeo((prev) => (prev?.d === next?.d && prev?.w === next?.w && prev?.h === next?.h ? prev : next));
  });

  // The thread scrolls inside the page, and the page scrolls too: both move the line's start.
  useLayoutEffect(() => {
    if (!clip) return;
    const bump = () => setGeo((g) => (g ? { ...g } : g));
    const onScroll = () => requestAnimationFrame(bump);
    clip.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      clip.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [clip]);

  if (!geo) return null;
  return (
    <svg className={styles.overlay} width={geo.w} height={geo.h} viewBox={`0 0 ${geo.w} ${geo.h}`} aria-hidden="true" focusable="false">
      <path d={geo.d} className={styles.halo} />
      <m.path
        key={drawKey}
        d={geo.d}
        className={styles.line}
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: dur.short + 0.04, ease: ease.out }}
      />
      <circle cx={geo.end.x} cy={geo.end.y} r="3.5" className={styles.dot} />
    </svg>
  );
}
