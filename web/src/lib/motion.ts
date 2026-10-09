// Mirrors the --dur-* and --ease-* tokens in styles/tokens.css. Change both together.
// Motion takes SECONDS; CSS takes milliseconds.
export const dur = { micro: 0.12, short: 0.22, long: 0.42 } as const;

export const ease = {
  out: [0.16, 1, 0.3, 1],
  inOut: [0.65, 0, 0.35, 1],
} as const;

/** The signature moment, in milliseconds from the reply landing. See DESIGN.md. */
export const audit = {
  meterStart: 120,
  firstToken: 240,
  tokenGap: 180,
  maxAnimatedTokens: 4,
  checkGap: 60,
  settle: 1000,
} as const;

/** True when the visitor asked the system for less motion. Read at the moment it is needed, never cached. */
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
