import { Link } from "react-router-dom";
import styles from "./Footer.module.css";

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <p>OneBar is not a rescue service. If someone is in danger, call the local emergency number.</p>
        <nav aria-label="Footer" className={styles.links}>
          <Link to="/results">Results</Link>
          <Link to="/how-it-works">How it works</Link>
          <a href="https://github.com/JUICEWRLD998/onebar" rel="noopener">
            Source code
          </a>
        </nav>
      </div>
    </footer>
  );
}
