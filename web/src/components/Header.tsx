import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { health } from "../lib/api";
import { useTheme, type Theme } from "../lib/theme";
import styles from "./Header.module.css";
import { SignalMark } from "./SignalMark";

const THEME_LABEL: Record<Theme, string> = { system: "System", light: "Light", dark: "Dark" };

function ThemeIcon({ theme }: { theme: Theme }) {
  // sun, moon, and a half-and-half disc for "follow the system"
  if (theme === "light")
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    );
  if (theme === "dark")
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
        <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />
      </svg>
    );
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 0 0 16z" fill="currentColor" />
    </svg>
  );
}

type Live = "checking" | "live" | "offline";

const cls = (styles: Record<string, string>) => ({ isActive }: { isActive: boolean }) =>
  isActive ? `${styles.link} ${styles.current}` : (styles.link as string);

export function Header() {
  const { theme, cycle } = useTheme();
  const [live, setLive] = useState<Live>("checking");
  useEffect(() => {
    let cancelled = false;
    const check = () =>
      health().then((ok) => {
        if (!cancelled) setLive(ok ? "live" : "offline");
      });
    void check();
    const id = window.setInterval(check, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <NavLink to="/" className={styles.brand} aria-label="OneBar, home">
          <SignalMark size={20} />
          <span>OneBar</span>
        </NavLink>
        <nav className={styles.nav} aria-label="Main">
          <NavLink to="/" end className={cls(styles)}>
            Ask
          </NavLink>
          <NavLink to="/results" className={cls(styles)}>
            Results
          </NavLink>
          <NavLink to="/how-it-works" className={cls(styles)}>
            How it works
          </NavLink>
        </nav>
        <div className={styles.tools}>
          <span className={styles.status} data-state={live} role="status">
            <span className={styles.dot} aria-hidden="true" />
            {live === "live" ? "Live" : live === "offline" ? "Offline" : "Checking"}
          </span>
          <button
            type="button"
            className={styles.theme}
            onClick={cycle}
            aria-label={`Theme: ${THEME_LABEL[theme]}. Switch theme.`}
          >
            <ThemeIcon theme={theme} />
            <span className={styles.themeText}>{THEME_LABEL[theme]}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
