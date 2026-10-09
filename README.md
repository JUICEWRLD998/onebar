# OneBar

Text a question from one bar of signal. Get one checked reply of at most 160 characters.

**Status: NOT LIVE.** Nothing is deployed yet. Built so far (Phase 0-7):

| Part | Status |
|---|---|
| Facts engine: forecast + time + trip to canonical fact strings | built, tested |
| Checker: 160 GSM-7 septets, every number traced to a fact or to the question, required facts present | built, tested |
| Template reply from facts alone (the fallback) | built, tested |
| Model reply (base Qwen3-8B on Tinker) with one corrected retry, then the template; CLI `python -m onebar ask` | built, tested, measured on 20 questions |
| Dataset (real places, past forecasts, checker-passing teacher replies) and eval harness with base numbers | built, tested, eval table has template, base and larger-model rows |
| Tuned Qwen3-8B (LoRA SFT on Tinker): 98.1% first-try checker pass on the frozen test set vs 56.8% for the base model | built, measured; weights on Tinker, HF export pending a token |
| Temporal trip workflow: durable trips, idempotent replies, overdue alert that survives a worker kill  | built, tested, run live |
| Email channel (Gmail alias, read-only poller, in-thread replies with a trace link) and web API; live email run answered three questions in 13-24 s app side | built, tested, run live from the owner's own address |
| Web UI: Ask (handset, leader-line proof, terrain, hour strip, tuned vs base), Results, How it works, trace page; light and dark; 0 axe violations; 117 tests | built, measured, run live against the real stack |
| Deploy, demo video | NEXT |

How it will work: code locates the hiker and computes the facts (Open-Meteo forecast, sunrise and sunset, elevation, their trip). A model writes one reply. A deterministic checker gates it: any invented number, wrong length or missing fact and the reply is rejected; after two failures the code's own template goes out.

Run the tests: `make test` (or `python -m pytest`) and `make web-build` (type check, web tests, production build). Run it locally: `make worker`, `make web` (API on :8000) and `make web-dev` (UI on :5173, proxies `/api`). Every number claimed here is listed in [CLAIMS.md](CLAIMS.md); design choices and thresholds in [DECISIONS.md](DECISIONS.md).

Built for DEV Hacktoberfest W1 "Touch Grass". Author: Mustapha Fadhlullah, independent security researcher.
