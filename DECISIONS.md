# DECISIONS

Phase 0 gate log. Timestamps are UTC.

## Open-Meteo (task 4)
- 2026-10-08T18:28Z forecast call HTTP 200, 2.8 s; elevation call HTTP 200, 0.9 s. Point 46.55,7.98 -> 3219 m.
- Fixtures: fixtures/open_meteo_46.55_7.98.json, fixtures/elevation_46.55_7.98.json

## Temporal (task 3, partial)
- 2026-10-08T18:37Z local dev server (CLI 1.9.1, server 1.32.0) starts and reports SERVING on localhost:7233. Cloud trial not tried; awaiting decision.

## Tinker (tasks 1-2), 2026-10-08
- Task 1 PASS. `ServiceClient` lists 31 models incl. `Qwen/Qwen3-8B`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`. Sampled 20 tokens from `Qwen/Qwen3-8B` (first call 57.9 s including tokenizer download, cold). Script: `scripts/gate_tinker.py`.
- Task 2 PASS. OpenAI-compatible endpoint accepts the base model name `Qwen/Qwen3-8B` on `/completions`. Latency over 3 calls: 1.44 s, 0.86 s, 1.06 s (30 max tokens). Script: `scripts/gate_oai.py`.
- Note: raw completions on the base model ramble into reasoning text after the answer. Phase 2 must use the non-thinking chat renderer and a stop sequence.
- Credit-claim step cannot be verified from code; calls authenticate, so access works.

## Phase 1 decisions (facts engine and checker), 2026-10-08
- Horizon is 12 hours from the current forecast hour. A storm in the current hour counts, even if the hour began before the question.
- Storm = WMO weather code 95-99, or CAPE >= 1000 J/kg with precipitation probability >= 60%. Rain = >= 0.2 mm in the hour with probability >= 50%. These are thresholds I chose; they are not tuned and not validated against outcomes. The walk (Phase 9) is the only field check.
- `turn_by` = return time minus a 90 minute descent assumption (`Trip.descent_min`). It is an assumption, not a measurement. The reply never states the 90.
- A time of day in a question ("by 3") resolves to the next occurrence at or after now; an unmarked hour 1-11 picks the earlier of AM and PM that is still ahead.
- Number rule: a number is the digits plus the unit glued to it, compared as one string. `55 km/h`, `55mph` and a dropped minus sign all count as invented. A number in the hiker's question is allowed as written, and a clock time in the question also allows its 24-hour form.
- Required facts: a question's intents name groups of fact keys; the reply must state at least one fact of each group that exists. A group with no existing fact is not demanded.
- Template go/no-go: "No-go" when a storm starts at or before the target time (or the trip car time); "Caution" for a later storm or gusts >= 60 km/h; otherwise "Looks OK". It says nothing about rain, cold or daylight in the verdict.
- Elevation comes in the forecast response, so there is no separate elevation module. `locate.py` (place name to coordinates) moves to Phase 5 with the `TRIP` command.
- Tests that need a storm use a synthetic forecast; the 20 frozen real forecasts have no thunderstorm, so storm paths are covered by editing one hour of a real forecast.
