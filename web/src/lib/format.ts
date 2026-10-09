import type { Path } from "./types";

/** 46.27 N, 8.19 E: plain letters, no degree sign, so it reads the same in every font and on a feature phone. */
export function formatCoords(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(2)} ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)} ${lon >= 0 ? "E" : "W"}`;
}

/** Who wrote the reply that went out, in words. The template is the code's own fallback. */
export function pathText(path: Path): string {
  switch (path) {
    case "model":
      return "Written by the tuned model.";
    case "model-retry":
      return "Written by the tuned model after one correction.";
    case "template":
      return "Written by the code's own template, because the model failed twice.";
  }
}

/** The server's "could not find" line mentions a command the web phone hides; say what to do here instead. */
export function placeProblem(serverText: string): string {
  return /^Could not find/i.test(serverText)
    ? "Could not find that place. Try a larger town nearby, or type coordinates like 46.55, 7.98."
    : serverText;
}
