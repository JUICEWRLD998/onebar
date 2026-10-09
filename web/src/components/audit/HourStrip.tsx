import type { Hour } from "../../lib/types";
import styles from "./Audit.module.css";

interface Props {
  hours: Hour[];
  /** The forecast hour (ISO, the place's clock) the focused number was read at. */
  activeHour: string | null;
}

const kindOf = (h: Hour) => (h.storm ? "storm" : h.rain ? "rain" : "calm");
const hh = (t: string) => t.slice(11, 13);
const hhmm = (t: string) => t.slice(11, 16);

export function HourStrip({ hours, activeHour }: Props) {
  if (hours.length === 0) return null;
  const peak = Math.max(...hours.map((h) => h.gust ?? 0));
  const domain = Math.max(20, Math.ceil(peak / 10) * 10);
  const peakAt = hours.findIndex((h) => (h.gust ?? -1) === peak && peak > 0);

  return (
    <section className={styles.strip} aria-labelledby="strip-title">
      <h3 id="strip-title" className={styles.h3}>
        The next {hours.length} hours
      </h3>
      <ol className={styles.cols} aria-hidden="true">
        {hours.map((h, i) => (
          <li key={h.t} className={styles.col} data-active={activeHour === h.t} data-kind={kindOf(h)}>
            <span className={styles.peak}>{i === peakAt ? `${Math.round(peak)}` : ""}</span>
            <span className={styles.barWrap}>
              {h.gust === null ? (
                <span className={styles.noData} />
              ) : (
                <span className={styles.bar} style={{ height: `${Math.max(3, (h.gust / domain) * 100)}%` }} />
              )}
            </span>
            <span className={styles.hour}>{hh(h.t)}</span>
          </li>
        ))}
      </ol>
      <ul className={styles.legend} aria-label="Key">
        <li>
          <i className={styles.swatch} data-kind="calm" /> Wind gust, km/h
        </li>
        <li>
          <i className={styles.swatch} data-kind="rain" /> Rain likely
        </li>
        <li>
          <i className={styles.swatch} data-kind="storm" /> Storm
        </li>
      </ul>
      <details className={styles.details}>
        <summary>Show the hours as a table</summary>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Hour</th>
              <th scope="col">Temp, °C</th>
              <th scope="col">Gust, km/h</th>
              <th scope="col">Rain chance</th>
              <th scope="col">Conditions</th>
            </tr>
          </thead>
          <tbody>
            {hours.map((h) => (
              <tr key={h.t} data-active={activeHour === h.t}>
                <th scope="row">{hhmm(h.t)}</th>
                <td>{h.temp === null ? "n/a" : Math.round(h.temp)}</td>
                <td>{h.gust === null ? "n/a" : Math.round(h.gust)}</td>
                <td>{h.pop === null ? "n/a" : `${Math.round(h.pop)}%`}</td>
                <td>{h.storm ? "Storm" : h.rain ? "Rain" : "Dry"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
