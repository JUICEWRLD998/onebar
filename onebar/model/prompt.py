"""Prompt for the reply writer. One function builds it, so serving, data generation and training agree.

The text is rendered in Qwen3's chat format with thinking closed (the cookbook's
`qwen3_disable_thinking` shape): the assistant turn opens with an empty think block, so the model
answers directly. The Tinker chat endpoint did not return text for Qwen3-8B (see DECISIONS.md),
so the prompt is sent to the completions endpoint as one string.
"""
from __future__ import annotations

from onebar.facts.model import FactSet

STOP = "<|im_end|>"

SYSTEM = (
    "You write one SMS reply to a hiker with one bar of signal.\n"
    "Rules:\n"
    "- At most 160 characters. Plain ASCII only: no emoji, no degree sign, no curly quotes.\n"
    "- Start with the answer to the question.\n"
    "- Use only the facts given. Copy each fact exactly as written, for example 14:40 or 55km/h.\n"
    "- Never write any other number. Never convert units or do arithmetic.\n"
    "- State the facts the question needs. Say nothing else."
)

LABELS: dict[str, str] = {
    "now": "time now",
    "temp_now": "temperature now",
    "feels_min": "coldest feels-like in the next hours",
    "gust_max": "strongest wind gust in the next hours",
    "gust_max_at": "time of the strongest gust",
    "pop_max": "highest chance of rain in the next hours",
    "storm_first": "first thunderstorm hour",
    "storm_none": "thunderstorm",
    "rain_first": "first rain hour",
    "rain_none": "rain",
    "sunset": "next sunset",
    "sunrise": "next sunrise",
    "dark_now": "light",
    "daylight_left": "daylight left",
    "elevation": "elevation",
    "car_by": "hiker's car time",
    "turn_by": "latest turn-around time",
    "turn_now": "turn-around",
    "target": "time the hiker asked about",
}


def chatml(messages: list[dict]) -> str:
    """Qwen chat format ending on an assistant turn that opens with an empty think block (thinking off)."""
    turns = "".join(f"<|im_start|>{m['role']}\n{m['content']}{STOP}\n" for m in messages)
    return turns + "<|im_start|>assistant\n<think>\n\n</think>\n\n"


def facts_block(facts: FactSet) -> str:
    return "\n".join(f"{LABELS.get(f.key, f.key)}: {f.token}" for f in facts)


def user_message(facts: FactSet, question: str) -> str:
    return f"Facts:\n{facts_block(facts)}\n\nQuestion: {question.strip()}"


_REASON_TEXT = {
    "empty": "the reply was empty",
    "too_long": "the reply was over 160 characters",
    "charset": "the reply used characters outside plain SMS text",
    "invented_number": "the reply contained a number that is not in the facts",
    "missing_fact": "the reply left out a fact the question needs",
    "contradiction": "the reply contradicts the facts",
}


def explain(reason: str) -> str:
    """Human wording for one checker reason code, with its detail."""
    code, _, detail = reason.partition(":")
    text = _REASON_TEXT.get(code, code)
    if code == "missing_fact":
        names = ", ".join(LABELS.get(k, k) for k in detail.split("|"))
        return f"{text} (one of: {names})"
    return f"{text} ({detail})" if detail else text


def render(facts: FactSet, question: str, previous: str | None = None, reasons: tuple[str, ...] = ()) -> str:
    """The full prompt string. With `previous` and `reasons` it asks for a corrected reply."""
    user = user_message(facts, question)
    if previous is not None:
        user += (
            f"\n\nYour previous reply was rejected: {previous!r}\n"
            "Problems: " + "; ".join(explain(r) for r in reasons) + ".\n"
            "Write a new reply that fixes every problem."
        )
    return chatml([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
