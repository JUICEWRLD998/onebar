import { useEffect } from "react";
import { Link } from "react-router-dom";
import { ContourField } from "../components/ContourField";
import evalData from "../data/eval.json";
import page from "./Page.module.css";
import styles from "./Results.module.css";

interface EvalData {
  questions: number | null;
  systems: string[];
  rows: { metric: string; values: string[] }[];
  caveat: string;
}
const data = evalData as EvalData;

const pct = (s: string | undefined) => (s ? Number.parseFloat(s) : 0);
const rowOf = (metric: string) => data.rows.find((r) => r.metric === metric);
const TUNED = data.systems.length - 1;

function Bars({ title, note, metric }: { title: string; note?: string; metric: string }) {
  const row = rowOf(metric);
  if (!row) return null;
  return (
    <figure className={styles.chart}>
      <figcaption className={styles.chartTitle}>{title}</figcaption>
      <ul className={styles.bars}>
        {data.systems.map((name, i) => {
          const v = pct(row.values[i]);
          return (
            <li key={name} className={styles.barRow} data-tuned={i === TUNED}>
              <span className={styles.barName}>{name}</span>
              <span className={styles.track} aria-hidden="true">
                <span className={styles.fill} style={{ transform: `scaleX(${Math.max(0.005, v / 100)})` }} />
              </span>
              <span className={styles.barValue}>{row.values[i]}</span>
            </li>
          );
        })}
      </ul>
      {note && <p className={styles.note}>{note}</p>}
    </figure>
  );
}

export function Results() {
  useEffect(() => {
    document.title = "Results | OneBar";
  }, []);

  return (
    <div className={page.page}>
      <ContourField />
      <div className={page.head}>
        <h1 className={page.h1}>Does the tuned model beat the base model?</h1>
        <p className={page.lede}>
          Yes on the first try: {data.rows[0]?.values[TUNED]} of replies pass the checker, against {data.rows[0]?.values[1]} for the
          untuned base model. These are {data.questions} questions at places the model never saw in training.
        </p>
      </div>

      <section className={page.section} aria-labelledby="charts-title">
        <h2 id="charts-title">First draft, as written</h2>
        <div className={styles.charts}>
          <Bars
            title="Passed the checker on the first try"
            metric="Passed the checker on the first try"
            note="The code template passes by construction: it is written by the same code that checks it, so its replies are safe and stiff. It is the floor the model has to beat on wording, not on safety."
          />
          <Bars
            title="Facts the question needs, stated in the first draft"
            metric="Required-fact coverage of the first draft"
          />
        </div>
      </section>

      <section className={page.section} aria-labelledby="table-title">
        <h2 id="table-title">The full table</h2>
        <div className={styles.scroll} role="region" aria-label="Full results table" tabIndex={0}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Measure</th>
                {data.systems.map((s, i) => (
                  <th key={s} scope="col" data-tuned={i === TUNED}>
                    {s}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.metric}>
                  <th scope="row">{r.metric}</th>
                  {r.values.map((v, i) => (
                    <td key={i} data-tuned={i === TUNED}>
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={page.section} aria-labelledby="limits-title">
        <h2 id="limits-title">What these numbers do not show</h2>
        <div className={page.prose}>
          <p>{data.caveat}</p>
          <p>
            Latency says little about load, because it was timed one request at a time. Every figure comes from one run on one frozen
            test set; there are no error bars.
          </p>
          <p>
            The tuned model&rsquo;s weights are not published yet. Until they are, the only way to try it is this site. See{" "}
            <Link to="/how-it-works">how it works</Link> for what the code does around the model.
          </p>
        </div>
      </section>
    </div>
  );
}
