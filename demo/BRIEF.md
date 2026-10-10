# OneBar demo brief

Written 2026-10-10 from the code, README.md, CLAIMS.md, web/DESIGN.md and a walk of https://onebar-v46s.onrender.com/.

**Name.** OneBar.

**One-liner.** Text a question from one bar of signal. Get one checked reply of at most 160 characters.

**User.** A hiker out on a route with weak signal and no data, who needs one weather answer they can trust.

**Problem.** One bar of signal will not load a weather app or a map. A chatbot answer can contain a number nobody
computed (an invented storm time, a wrong gust speed). On a ridge, that is a safety problem.

**How it works (from the code).**
1. A message arrives (web page, or email to a mailbox alias).
2. Code computes every fact: Open-Meteo hourly forecast, sunrise and sunset, elevation, the trip's turn-around time
   (`onebar/facts/`).
3. A tuned Qwen3-8B (LoRA, trained on Tinker) words one reply under 160 GSM-7 characters.
4. A deterministic checker judges it: under 160 characters, plain SMS characters, every number traced to a fact or
   to the question, the facts the question needs, agrees with the forecast (`onebar/check/`).
5. A failed draft gets one retry. After two failures the code's own template goes out.
6. Temporal runs each trip as a durable workflow: `TRIP` starts a timer, `OUT` cancels it, and if the timer runs out
   the contact gets one email.

**Signature moment.** The reply gets audited: each number in the reply draws a leader line to the forecast fact and
hour it came from, then the verdict line reads "Checked. N of N numbers traced to the forecast."

**Three demo beats.**
1. Ask live: place set to Zermatt, type "storm before 3?", send, one reply comes back and is checked.
2. The proof: hover each number in the reply; its leader line runs to the fact row and the forecast hour.
3. Tuned against base: a recorded test-set question, flipped to the base model, whose draft is 241 of 160
   characters and fails the checker.

**What is real.**
- Deployed web app on Render (free plan, no disk: Temporal state resets on restart).
- Results page numbers (CLAIMS.md): tuned 98.1% first-try checker pass on 414 frozen test questions at places
  unseen in training, against 56.8% for base Qwen3-8B and 57.2% for Qwen3.6-35B-A3B. Tuned invented-number rate 0.0%.
- Worker killed mid-trip and restarted; the overdue alert was still delivered once (local Temporal dev server,
  delivery to a local outbox file).
- Recorded examples on the Ask page are real rows from the frozen test set and the site labels them "Not live".

**Not real / do not claim.** SMS delivery (Twilio is not wired). Satellite. A real outing with the product (the
walk in the plan has not been logged in the repo). Server-restart survival on Render (state resets there).

**Sponsor tech.** Tinker (fine-tuning the open Qwen model), Temporal (the trip timer). Each named once.

**Event.** DEV Hacktoberfest W1 "Touch Grass". The event page sets no video length rule (searched
`strategy/raw/page.txt`); the default 120 s cap applies.

**Live status at scout time (2026-10-10).** Pages and recorded replays load. Every live place lookup
(Zermatt, Banff, coordinates) ended in "Forecast unavailable right now. Try again in a few minutes." after 15 to
50 s. Open-Meteo answers 200 from this machine, so the Render egress IP is the likely cause (UNVERIFIED: no access
to Render logs). He chose to fix the deploy before recording.
