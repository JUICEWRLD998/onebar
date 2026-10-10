# OneBar demo, 247 words, runtime set after voicing

Source of truth is `plan.json` (`vo` fields). Times fill in after `tts.mjs` runs.

| # | Time | Voice-over | Picture |
|---|------|-----------|---------|
| 1 | 0:00 | This is OneBar. Ask about the weather on your route, and get one checked answer that fits in a single text. | Title card: OneBar, "One bar of signal. One checked reply.", a still of a checked reply with its leader line |
| 2 | | You're up on a ridge with one bar of signal. Your weather app won't load, and the clouds are building. | Statement card: "You're on a ridge. / One bar of signal. / The weather app won't load." |
| 3 | | You could ask a chatbot, but it might make up a number. Up here, a made-up storm time can hurt you. | Statement card: "A chatbot can make up a number. / Up here, that's a storm you didn't see." |
| 4 | | OneBar splits the work. Code reads the forecast for your exact spot, a small model writes the reply, and a checker makes sure every number in it is real. | Live Ask page, place already set to Zermatt; cursor moves heading, place chip, message box, audit sheet |
| 5 | | I'm near Zermatt, so I type storm before three and hit send. One short reply comes back, already checked. | Live: types "storm before 3?", clicks Send, reply arrives and is audited; zoom 1.7x on the phone panel on "checked" |
| 6 | | Hover any number in it, and a line runs back to the forecast hour it came from. The model didn't guess any of them. | Live: unzoom, scroll; cursor hovers each number, its leader line draws to the fact row |
| 7 | | This one's a recorded question from our test set. Flip to the untuned base model, and its draft runs to two hundred and forty-one characters. That's too long for one text, so it never goes out. | Recorded example "ridge ok by 3:30pm then car?" (site labels it "Not live"); Base model toggle; red "241 of 160" meter |
| 8 | | That's why OneBar runs its own model, an open Qwen fine-tuned on Tinker. On four hundred and fourteen questions at places it never saw, it passed the check first time ninety-eight percent of the time. The base model got just under fifty-seven. | Live Results page; zoom 1.5x on the tuned 98.1% bar, cursor to base 56.8% |
| 9 | | If you're heading out alone, text trip with your return time and a contact. Miss your time without texting out, and your contact gets an email. Temporal keeps that timer running, even if the worker crashes. | Live How it works page, scrolled to "The trip timer" |
| 10 | | OneBar. One bar, one reply, every number checked. Try it at the link below. | End card: name, tagline, onebar-v46s.onrender.com, credit |

Claims and their sources: 98.1% vs 56.8% on 414 frozen test questions at unseen places (`CLAIMS.md`, `eval/results/tuned.json`,
`eval/results/base.json`); 241 of 160 is the base draft for the recorded example shown on the live site; the worker-crash
claim is the local live run in `data/demo5.log` (Render's free plan has no disk, so the video does not claim survival of a
server restart).
