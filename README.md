# OneBar

Text a question from one bar of signal. Get one checked reply of at most 160 characters.

**Status: NOT LIVE.** Nothing is deployed and no model is tuned yet. Built so far (Phase 0-3):

| Part | Status |
|---|---|
| Facts engine: forecast + time + trip to canonical fact strings | built, tested |
| Checker: 160 GSM-7 septets, every number traced to a fact or to the question, required facts present | built, tested |
| Template reply from facts alone (the fallback) | built, tested |
| Model reply (base Qwen3-8B on Tinker) with one corrected retry, then the template; CLI `python -m onebar ask` | built, tested, measured on 20 questions |
| Dataset (real places, past forecasts, checker-passing teacher replies) and eval harness with base numbers | built, tested, eval table has template, base and larger-model rows |
| Tuned model, Temporal trip workflow, email and web channels | NEXT |

How it will work: code locates the hiker and computes the facts (Open-Meteo forecast, sunrise and sunset, elevation, their trip). A model writes one reply. A deterministic checker gates it: any invented number, wrong length or missing fact and the reply is rejected; after two failures the code's own template goes out.

Run the tests: `make test` (or `python -m pytest`). Every number claimed here is listed in [CLAIMS.md](CLAIMS.md); design choices and thresholds in [DECISIONS.md](DECISIONS.md).

Built for DEV Hacktoberfest W1 "Touch Grass". Author: Mustapha Fadhlullah, independent security researcher.
