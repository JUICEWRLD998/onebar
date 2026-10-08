"""Phase 0 gate: one live Tinker call. Lists models, samples 20 tokens from Qwen/Qwen3-8B."""
import os, time, sys
from pathlib import Path

for line in Path(__file__).resolve().parents[1].joinpath(".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip())

import tinker
from tinker import types

t0 = time.time()
svc = tinker.ServiceClient()
caps = svc.get_server_capabilities()
names = [m.model_name for m in caps.supported_models]
print("models:", len(names))
print([n for n in names if "Qwen3-8B" in n or "gpt-oss" in n.lower()])
print("list_s", round(time.time() - t0, 2))

base = "Qwen/Qwen3-8B"
t1 = time.time()
sc = svc.create_sampling_client(base_model=base)
tok = sc.get_tokenizer()
prompt = types.ModelInput.from_ints(tok.encode("Weather text in 160 chars: ridge storm at 14:40, gusts 55km/h."))
res = sc.sample(prompt=prompt, num_samples=1, sampling_params=types.SamplingParams(max_tokens=20, temperature=0.0)).result()
print("sample:", repr(tok.decode(res.sequences[0].tokens)))
print("sample_s", round(time.time() - t1, 2))
