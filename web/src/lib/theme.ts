import { useCallback, useEffect, useState } from "react";
import { safeGet, safeRemove, safeSet } from "./session";

export type Theme = "system" | "light" | "dark";
const KEY = "onebar-theme";

export const nextTheme = (t: Theme): Theme => (t === "system" ? "light" : t === "light" ? "dark" : "system");

/** A link can pin the look for one visit (?theme=light|dark), so a screenshot or a score run is not left to the system. */
function fromUrl(): Theme | null {
  try {
    const v = new URLSearchParams(window.location.search).get("theme");
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function read(): Theme {
  const pinned = fromUrl();
  if (pinned) return pinned;
  const v = safeGet(KEY);
  return v === "light" || v === "dark" ? v : "system";
}

export function applyTheme(t: Theme, root: HTMLElement = document.documentElement): void {
  if (t === "system") delete root.dataset.theme;
  else root.dataset.theme = t;
}

export function useTheme(): { theme: Theme; cycle: () => void } {
  const [theme, setTheme] = useState<Theme>(read);
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  const cycle = useCallback(() => {
    setTheme((t) => {
      const n = nextTheme(t);
      if (n === "system") safeRemove(KEY);
      else safeSet(KEY, n);
      return n;
    });
  }, []);
  return { theme, cycle };
}
