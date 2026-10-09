interface Props {
  /** How many of the four bars are lit. OneBar is the one-bar product, so the default is one. */
  lit?: number;
  size?: number;
  title?: string;
}

/** Four signal bars, the first lit in the accent colour. Used as the wordmark glyph and in the handset status. */
export function SignalMark({ lit = 1, size = 18, title }: Props) {
  const bars = [5, 9, 13, 17];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 22 20"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {bars.map((h, i) => (
        <rect
          key={h}
          x={i * 5.5}
          y={20 - h}
          width="3.5"
          height={h}
          rx="1"
          fill={i < lit ? "var(--accent)" : "var(--line-strong)"}
        />
      ))}
    </svg>
  );
}
