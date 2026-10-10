# OneBar

Ask about the weather on your route from one bar of signal, and get one reply of at most 160 characters in which
every number has been checked against the forecast.

**Live:** https://onebar-v46s.onrender.com (web). Built for DEV Hacktoberfest W1, "Touch Grass".

```
You:     when should I turn back?            (place set to Zermatt)
OneBar:  Turn back now. Sunset is 18:52 with 34m left. No storm, gusts 23km/h.
         Checked. 3 of 3 numbers traced to the forecast.
```

That exchange is a real reply from the deployed site on 2026-10-10, written by the tuned model.

## The problem

Out on a ridge with one bar, a weather app or a map will not load, but a short text still gets through. An AI
assistant can answer in a sentence, but it can also write a number nobody computed: a storm time, a gust speed, a
sunset. On a mountain, a made-up number is a safety problem. OneBar keeps the language model away from the numbers.

## How a reply is made

1. **A message arrives** from the web page, or as an email to a mailbox alias.
2. **Code computes every fact.** Hourly forecast, sunrise and sunset, elevation, and the hiker's turn-around time come
   from Open-Meteo and from arithmetic in `onebar/facts/`. Each fact becomes a fixed string such as `18:52` or `23km/h`.
3. **A small model writes the words.** A Qwen3-8B fine-tuned for this job is given the facts and the question and asked
   for one message under 160 characters.
4. **A checker judges the draft** (`onebar/check/`, plain code, no model):
   - under 160 SMS characters (GSM-7 septets), so a basic phone can carry it in one message;
   - plain SMS characters only;
   - every number is one of the computed facts or a number the hiker wrote;
   - the facts this kind of question needs are present (a storm question has to mention storms);
   - it does not deny a storm or rain that the forecast shows, or invent one.
5. **Send, retry once, or fall back.** A failed draft gets one corrected retry. After two failures the code writes the
   reply itself from a template, which passes the checker by construction.

The web page shows the proof for every reply: each number is linked by a line to the forecast fact and hour it came
from, next to a contour map of the place, the next 12 hours, and the five checks. A Tuned/Base switch shows what the
untuned base model wrote for the same question and why the checker would refuse it.

## Why train a model at all

The checker makes every reply safe, but the base model fails it often, and then the hiker gets the stiff template.
Training fixes that. Results on 414 held-out questions at places the model never saw in training (the test set is split
by 0.5 degree map cell), from `eval/TABLE.md`:

| | Code template | Base Qwen3-8B | Larger Qwen3.6-35B-A3B | Tuned Qwen3-8B (LoRA) |
|---|---|---|---|---|
| Passed the checker on the first try | 100.0% | 56.8% | 57.2% | **98.1%** |
| Fell back to the template | 100.0% | 17.1% | 3.4% | **0.0%** |
| First draft had an invented number | 0.0% | 1.4% | 0.7% | **0.0%** |
| Facts the question needs, stated in the first draft | 100.0% | 73.1% | 71.0% | **99.1%** |
| Cost per answer (published Tinker prices) | $0 | $0.00011 | $0.00027 | **$0.00007** |

The tuned 8B model also beats the 35B model on this job, at about a quarter of its cost per answer. The checker
measures structure and agreement with the facts; it does not judge whether a qualified claim such as "no storm by
noon" is right, so a pass is necessary, not sufficient.

**How it was trained** (`data/stats.json`, `eval/results/sft_run.json`, `train/sft.py`): 1,603 real mountain
locations, 4,809 situations built from past Open-Meteo forecasts, and replies drafted by two larger open models
(Qwen3.5-397B-A17B and Qwen3.6-35B-A3B) kept only when they passed the checker. That gave 3,290 training rows and
514 validation rows. LoRA rank 32 on Qwen3-8B, 2 epochs, learning rate 2e-4, batch 32, trained on Tinker for about
$0.86. The training prompt is the exact string the service sends.

## Trips: someone knows when you are overdue

Text `TRIP <place> BACK 17:00 CONTACT <email>` before you set out. OneBar starts a timer for your return time plus a
grace period. Text `OUT` when you are safe and the timer stops. If the timer runs out first, your contact gets one
email that says what you told OneBar. Each sender's trip is a durable Temporal workflow (`onebar/temporal/`): replies
are sent once even if a message is delivered twice, and in a local run the worker was killed mid-trip, restarted after
the deadline, and the alert still went out once (`scripts/demo_phase5.py`, `data/demo_outbox.jsonl`).

Other commands: `PLACE <name or lat,lon>` sets where you are without a trip, `FORGET` deletes what OneBar holds about
you, `HELP` lists the commands. Anything else is a weather question.

## What is live and what is not

- **Web: live** at the link above. Set a place, ask a question, and read the proof.
- **Email: built and tested**, including a live run from the owner's own address (replies in 13 to 24 s on the app
  side). It runs only where a mailbox is configured (`IMAP_USER`, `IMAP_APP_PASSWORD`).
- **SMS and satellite messengers: not built.** The 160-character GSM-7 limit is there so they can be added without
  changing a reply.
- **The tuned weights** are served from Tinker. A Hugging Face export is not done yet.
- **OneBar is not a rescue service** and not a replacement for a national mountain forecast. It reads one public
  forecast model. In danger, call the local emergency number.

### Deployment notes

One Docker container on Render's free plan runs a Temporal dev server (SQLite), the worker, the API and the built web
page (`Dockerfile`, `deploy/start.sh`). Two consequences:

- **Forecast quota.** Open-Meteo counts its free quota per IP, and a shared cloud IP is often over it. So the web page
  fetches the same Open-Meteo data from the visitor's own connection and sends it with the message
  (`web/src/lib/openMeteo.ts`). The server checks its shape, keeps only what the facts engine reads, and uses it for
  that visitor's session only (`onebar/channels/hints.py`). Email still fetches on the server.
- **No disk.** A restart forgets trips and places. The web page notices when the server has lost a visitor's place,
  sends the saved coordinates again, and repeats the question.

## Run it locally

Python 3.12 and Node 22.

```bash
pip install -e ".[dev,model,temporal,web]"
cp .env.example .env              # TINKER_API_KEY and ONEBAR_MODEL for the tuned model; empty means template only
temporal server start-dev         # or point TEMPORAL_ADDRESS at a running server
make worker                       # Temporal worker
make web                          # API on :8000 (serves web/dist if built)
make web-dev                      # UI on :5173, proxies /api
python -m onebar ask "storm before 3?" --at 46.55,7.98 --no-model   # one answer from the command line
```

Tests: `make test` (615 Python tests) and `make web-build` (type check, 130 web tests, production build).

## Repository map

```
onebar/facts/      forecast, sunrise and sunset, elevation, geocoding -> fact strings
onebar/check/      the checker: GSM-7 length, number tracing, required facts, agreement with the forecast
onebar/model/      prompt, Tinker client, keepalive
onebar/pipeline.py facts -> draft -> check -> retry -> template
onebar/temporal/   TripWorkflow, activities, worker
onebar/channels/   web API, email poller and sender, traces, browser hints
data/ eval/ train/ dataset, frozen test set, eval harness and results, fine-tuning script
web/               Vite, React, TypeScript, CSS Modules (Ask, Results, How it works, trace page)
```

## Built with

Tinker (fine-tuning and serving the open Qwen3-8B), Temporal (durable trips and replies), Open-Meteo (forecast,
elevation and geocoding), FastAPI, React.

MIT licence. Mustapha Fadhlullah — independent security researcher.
