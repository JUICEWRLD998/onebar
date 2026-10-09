"""Bulk sampling from a large open model on Tinker (OpenAI-compatible completions), with backoff and a parallel map."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, TypeVar

from onebar.model.client import BASE_URL, ModelError
from onebar.model.prompt import STOP

RETRYABLE = {408, 409, 429, 500, 502, 503, 504}
CHAT_MIN_TOKENS = 1000

T = TypeVar("T")
R = TypeVar("R")


class Sampler:
    """`sample(prompt, n)` returns n completions. The prompt is a finished ChatML string (see model.prompt.chatml)."""

    def __init__(self, model: str, client: Any = None, timeout: float = 90.0, retries: int = 5):
        self.model = model
        self.retries = retries
        if client is None:
            from openai import OpenAI

            key = os.environ.get("TINKER_API_KEY")
            if not key:
                raise ModelError("TINKER_API_KEY is not set")
            client = OpenAI(base_url=BASE_URL, api_key=key, timeout=timeout, max_retries=0)
        self._client = client

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status is not None:
            return status in RETRYABLE
        return type(exc).__name__ in {"APITimeoutError", "APIConnectionError", "TimeoutError", "ConnectionError"}

    def sample(self, prompt: str | list[dict], n: int = 1, temperature: float = 0.7, max_tokens: int = 120) -> list[str]:
        """n completions. The Tinker endpoint returns one completion whatever `n` says, so extra calls fill the rest."""
        out: list[str] = []
        for _ in range(n):
            out.extend(self._sample_once(prompt, temperature, max_tokens)[: n - len(out)])
            if len(out) >= n:
                break
        return out

    def _sample_once(self, prompt: str | list[dict], temperature: float, max_tokens: int) -> list[str]:
        """A str prompt goes to the completions endpoint. A list of chat messages goes to the chat endpoint,
        for models (gpt-oss) that have no ChatML-with-closed-think form; their reasoning is kept short and
        `max_tokens` is raised to leave room for it."""
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                if isinstance(prompt, str):
                    resp = self._client.completions.create(
                        model=self.model, prompt=prompt, temperature=temperature,
                        max_tokens=max_tokens, stop=[STOP],
                    )
                    return [c.text for c in resp.choices]
                resp = self._client.chat.completions.create(
                    model=self.model, messages=prompt, temperature=temperature,
                    max_tokens=max(max_tokens, CHAT_MIN_TOKENS), reasoning_effort="low",
                )
                return [c.message.content or "" for c in resp.choices]
            except Exception as exc:
                last = exc
                if not self._retryable(exc):
                    break
                time.sleep(min(2 ** attempt, 30))
        raise ModelError(f"{self.model}: {type(last).__name__}: {str(last)[:200]}")


def parallel_map(fn: Callable[[T], R], items: Iterable[T], workers: int = 8) -> list[R | Exception]:
    """Apply fn to every item on a thread pool. Results keep input order; an exception becomes that item's result."""

    def safe(item: T) -> R | Exception:
        try:
            return fn(item)
        except Exception as exc:  # one bad item must not abort a long run
            return exc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(safe, items))
