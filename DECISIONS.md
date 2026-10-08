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
