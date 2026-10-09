"""Reply-writer client: the Tinker OpenAI-compatible completions endpoint. Offline tests inject a fake draft."""
from __future__ import annotations

import os
import re
import threading
from typing import Callable

from onebar.model.prompt import STOP

BASE_URL = "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1"
DEFAULT_MODEL = "Qwen/Qwen3-8B"
TIMEOUT_S = 20.0
MAX_TOKENS = 120  # 160 characters is about 50 tokens; the rest is headroom for a bad draft

Draft = Callable[[str], str]  # prompt string -> raw reply text


class ModelError(RuntimeError):
    """The model could not produce text: network, HTTP, timeout or an empty completion."""


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def clean(raw: str) -> str:
    """Strip artifacts that are not part of the reply: stray think blocks, outer whitespace and wrapping quotes."""
    text = _THINK.sub("", raw).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


class TinkerDraft:
    def __init__(self, model: str | None = None, api_key: str | None = None, timeout: float = TIMEOUT_S):
        from openai import OpenAI  # imported here so the pure modules never need the SDK

        key = api_key or os.environ.get("TINKER_API_KEY")
        if not key:
            raise ModelError("TINKER_API_KEY is not set")
        self.model = model or os.environ.get("ONEBAR_MODEL") or DEFAULT_MODEL
        self._client = OpenAI(base_url=BASE_URL, api_key=key, timeout=timeout, max_retries=0)
        self._lock = threading.Lock()
        self.prompt_tokens = 0  # running totals across calls, for cost per answer in the eval
        self.completion_tokens = 0
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        try:
            resp = self._client.completions.create(
                model=self.model, prompt=prompt, max_tokens=MAX_TOKENS, temperature=0.0, stop=[STOP]
            )
        except Exception as exc:
            raise ModelError(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
        usage = getattr(resp, "usage", None)
        with self._lock:
            self.calls += 1
            self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
        text = clean(resp.choices[0].text if resp.choices else "")
        if not text:
            raise ModelError("model returned an empty completion")
        return text
