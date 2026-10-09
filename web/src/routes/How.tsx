import { useEffect } from "react";
import { Link } from "react-router-dom";
import { SMS_LIMIT } from "../lib/reasons";
import { ContourField } from "../components/ContourField";
import styles from "./How.module.css";
import page from "./Page.module.css";

const STEPS: { who: "code" | "model"; title: string; text: string }[] = [
  { who: "code", title: "A message arrives", text: "From this page, or as an email to a mailbox alias. One conversation per sender." },
  { who: "code", title: "Code reads the facts", text: "Forecast hours, daylight, elevation and your turn-around time are computed. Nothing here is guessed." },
  { who: "model", title: "A small model words the reply", text: `It is given the facts and asked for one message under ${SMS_LIMIT} characters.` },
  { who: "code", title: "The checker judges it", text: "Five checks, below. A reply that fails any one is not sent." },
  { who: "code", title: "Send, retry once, or fall back", text: "A failed draft gets one retry. After two failures the code writes the reply itself from a template." },
];

const CHECKS = [
  ["Under 160 characters", `Counted in SMS characters, so a phone that only sends ${SMS_LIMIT} can carry it.`],
  ["Plain SMS characters", "Nothing that turns a message into a longer, costlier one or shows as boxes."],
  ["Every number traced", "Each number must be a forecast fact, or a number you wrote. An invented number fails the reply."],
  ["Says what the question needs", "A storm question has to mention storms. The checker knows which facts each question kind requires."],
  ["Agrees with the forecast", "It cannot say no storm when the forecast has one, or the reverse."],
];

export function How() {
  useEffect(() => {
    document.title = "How it works | OneBar";
  }, []);

  return (
    <div className={page.page}>
      <ContourField />
      <div className={page.head}>
        <h1 className={page.h1}>How a reply gets made</h1>
        <p className={page.lede}>
          The code computes every fact. The model only chooses the words. A checker stands between the model and you.
        </p>
      </div>

      <section className={page.section} aria-labelledby="flow-title">
        <h2 id="flow-title">From message to reply</h2>
        <ol className={styles.flow}>
          {STEPS.map((s, i) => (
            <li key={s.title} className={styles.step} data-who={s.who}>
              <span className={styles.stepNo} aria-hidden="true">
                {i + 1}
              </span>
              <h3 className={styles.stepTitle}>{s.title}</h3>
              <p>{s.text}</p>
              <span className={styles.who}>{s.who === "code" ? "Done by code" : "Done by the model"}</span>
            </li>
          ))}
        </ol>
        <p className={styles.legend}>
          Solid outline: plain code, always the same. Dashed outline: the model, the only step that can be wrong.
        </p>
      </section>

      <section className={page.section} aria-labelledby="checks-title">
        <h2 id="checks-title">The five checks</h2>
        <dl className={styles.checks}>
          {CHECKS.map(([name, text]) => (
            <div key={name} className={styles.check}>
              <dt>{name}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
        <p>
          You can see all five run on <Link to="/">the Ask page</Link>, and switch to the base model&rsquo;s draft for the same
          question to see which of them it fails.
        </p>
      </section>

      <section className={page.section} aria-labelledby="trip-title">
        <h2 id="trip-title">The trip timer</h2>
        <div className={page.prose}>
          <p>
            Text <code>TRIP</code> with a place, a return time and a contact email, and OneBar starts a timer for that time plus a
            grace period. Text <code>OUT</code> when you are safe and the timer is cancelled.
          </p>
          <p>
            If the timer runs out first, your contact gets one email. It says what you told OneBar and says plainly that OneBar is not
            a rescue service. <code>FORGET</code> deletes what OneBar holds about you.
          </p>
        </div>
      </section>

      <section className={page.section} aria-labelledby="not-title">
        <h2 id="not-title">What it is not</h2>
        <ul className={styles.not}>
          <li>Not a rescue service. It never calls anyone but the contact you named, and only by email.</li>
          <li>Not a guarantee. A passing reply is correct about the numbers it states; it can still be vague or incomplete.</li>
          <li>Not a replacement for a mountain forecast from your national service. It reads one public forecast model.</li>
        </ul>
        <p>
          The measured numbers are on <Link to="/results">Results</Link>.
        </p>
      </section>
    </div>
  );
}
