# CLAIMS

Every number in the README or post links to a row here, and each row points at a committed file.

| Claim | Value | Source file | Status |
|---|---|---|---|
| Checker rejects a planted set of 10 defective replies, 10 of 10 | 10/10 | `tests/test_checker.py` (`PLANTED`, `test_planted_control_is_exactly_ten_and_all_fail`) | verified, run `make test` |
| Template reply passes the checker on 3,360 cases (20 real forecasts x 3 times of day x with/without storm x with/without trip x 14 questions) | 3360/3360 | `tests/test_template.py` | verified, run `make test` |
| Base Qwen3-8B on 20 hand-written questions: 12 pass first try, 18 after one retry, 2 template fallbacks | 12/20, 18/20, 2/20 | `eval/results/phase2_base.json`, `scripts/run_phase2.py` | measured 2026-10-09, n=20 smoke test, 4 questions use a synthetic storm hour |
| Base model latency on those 20, retries included | p50 1.24 s, max 4.87 s | `eval/results/phase2_base.json` | measured 2026-10-09, single run from one laptop |
| Dataset: 1,603 real OSM locations, 4,809 situations from past Open-Meteo forecasts; 3,290 train + 514 val rows with checker-passing teacher replies; 414 frozen test rows | 1603 / 4809 / 3804 / 414 | `data/locations.jsonl`, `data/train.jsonl`, `data/val.jsonl`, `eval/test.jsonl`, `data/stats.json` | built 2026-10-09; two teachers (see DECISIONS) |
| Base Qwen3-8B on the 414-question test set: first-try checker pass | 56.8% | `eval/results/base.json`, `eval/TABLE.md` | measured 2026-10-09 |
| Base Qwen3-8B: reply from the model after one retry / template fallback | 82.9% / 17.1% | `eval/results/base.json` | measured 2026-10-09 |
| Base Qwen3-8B: cost per answer, latency p50 (sequential, 40 questions) | $0.00011, 1.64 s | `eval/results/base.json`, `eval/prices.json` | measured 2026-10-09; price from the Tinker models page |
| Teacher choice on 50 questions: Qwen3.5-397B-A17B vs GPT-OSS-120B questions with a passing candidate | 44/50 vs 41/50 | `eval/results/teacher_choice.json` | measured 2026-10-09 |
| Larger Qwen3.6-35B-A3B on the same test set: first-try checker pass, served by model, cost per answer | 57.2%, 96.6%, $0.00027 | `eval/results/large.json`, `eval/TABLE.md` | measured 2026-10-09 |
| Total Tinker sampling spend for data and eval on the grant key | $2.76 | `data/spend.json` | by published prices, upper bound |
| Tuned Qwen3-8B (LoRA, SFT) first-try checker pass on the 414 test questions, against base | 98.1% vs 56.8% | `eval/results/tuned.json`, `eval/results/base.json` | measured 2026-10-09; one training run; the checker measures structure, not forecast skill |
| Tuned: invented-number rate, contradiction rate, required-fact coverage (first draft) | 0.0%, 0.0%, 99.1% | `eval/results/tuned.json` | measured 2026-10-09 |
| Tuned: cost per answer, calls per answer, mean septets | $0.000069, 1.02, 47 | `eval/results/tuned.json`, `eval/prices.json` | measured 2026-10-09 |
| SFT run: 3,290 rows, 2 epochs, LoRA rank 32, validation first-try pass epoch 1 / epoch 2 | 96.7% / 98.7% (150 val questions) | `eval/results/sft_run.json` | measured 2026-10-09 |
| Whole-grant Tinker spend through Phase 4 | $3.68 | `data/spend.json` | by published prices, upper bound |
| Live run: worker killed mid-trip, restarted after the alert time; overdue alert delivered | 1 alert, to the contact, after restart | `data/demo5.log`, `data/demo_outbox.jsonl`, `scripts/demo_phase5.py` | run 2026-10-09 on a local Temporal dev server; delivery was to a local outbox file, not a real channel |
| TripWorkflow tests on Temporal's time-skipping server: alert once, OUT cancels, duplicate id one reply, flaky send, outage, FORGET, continue-as-new | 12 tests pass | `tests/test_temporal.py` | `make test`; two planted defects were caught |
| Live email run (Gmail, Temporal dev server, tuned model): three questions in a row, send to reply accepted by SMTP | 15.2 s, 23.7 s, 13.0 s | `data/e2e_result.log`, `scripts/e2e_email.py` | run 2026-10-09 from the owner's own address, NOT an outside address; reply visible in the owner's mailbox 55-72 s after sending (Gmail self-delivery), outside-address latency unmeasured |
| Tuned adapter latency by idle time: warm / 20 s idle / 45 s idle | 1.0 s / 3.1 s / 6.6 s | measured 2026-10-09, one run, in `DECISIONS.md` | the keepalive ping exists because of this |
| Email channel safety: read-only mailbox, alias-only, loop-proof replies, per-sender limit | tests | `tests/test_email_io.py`, `tests/test_channels_pure.py` | fakes for IMAP and SMTP, plus the live run |
| Web API: 500-char cap, rate limits, no sender data in traces, 404 on malformed ids | tests | `tests/test_web_api.py` | `make test` |
| Web UI palette: all text pairs >= 4.5:1, shapes >= 3:1, role hues >= 35 apart (CIE Lab), accent chroma 5.2x the most chromatic surface, in light, system-dark and explicit-dark | all hold | `web/scripts/palette-check.mjs` (`npm run palette`) | measured 2026-10-09 |
| Web UI accessibility: axe-core on 6 states (first visit, replayed reply, base-model view, Results, How it works, trace), light and dark | 0 violations in 12 runs; the same script reports `color-contrast` and `image-alt` on a planted bad page | `web/scripts/axe.mjs` | measured 2026-10-09 at 1280 px only; screen readers not tried |
| Web UI machine score (ui-studio `ui-score`), Ask page, planted controls passed | light 86, dark 77; no auto-fail tell | `data/ui-score/r3-ask-*.json` (git-ignored) | measured 2026-10-09; dark is held down by a metric that counts a tinted dark ground as an accent, see DECISIONS |
| Web UI tests | 117 pass (95 logic, hooks and flow; 22 component) | `web/src/**/*.test.*` | `cd web && npm test`; a planted wrong-index hover handler was caught |
| Live browser run against the real stack: PLACE Zermatt, ask "how windy is it going to get?", reply "Gusts up to 18km/h. No storm expected.", audit, terrain, trace page | all rendered; 1 of 1 numbers traced | `web/scripts/live.mjs`, `data/ui-shots/live/` (git-ignored) | run 2026-10-09 on the local stack, one question; spend for the run about $0.0002 |
| Whole-grant Tinker spend after the Phase 7 live run | $3.68 (3.678496) | `data/spend.json` | by published prices, upper bound |
