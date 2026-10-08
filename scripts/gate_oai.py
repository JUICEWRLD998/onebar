"""Phase 0 gate: one call to the Tinker OpenAI-compatible endpoint, with latency."""
import os, time, sys
from pathlib import Path

for line in Path(__file__).resolve().parents[1].joinpath(".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip())

from openai import OpenAI

model = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen3-8B"
c = OpenAI(base_url="https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1",
           api_key=os.environ["TINKER_API_KEY"], timeout=60)
for i in range(3):
    t = time.time()
    try:
        r = c.completions.create(model=model, prompt="Reply in one short SMS: storm at 14:40, gusts 55km/h. Reply:", max_tokens=30, temperature=0)
        print(i, round(time.time() - t, 2), "s", repr(r.choices[0].text))
    except Exception as e:
        print(i, round(time.time() - t, 2), "s ERR", type(e).__name__, str(e)[:300])
