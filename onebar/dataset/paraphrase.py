"""Hiker-register paraphrases of seed questions, accepted only when they cannot change what the checker demands.

A paraphrase is rejected unless it keeps every number exactly (the checker allows numbers written in the question,
so a new number would open a door) and classifies to the same intents as the seed (the required facts follow the
intents). Rejected paraphrases fall back to the seed question.
"""
from __future__ import annotations

import re

from onebar.check.intents import classify, parse_target
from onebar.check.numbers import extract
from onebar.model.prompt import chatml

MAX_CHARS = 100
_OPEN_ASSISTANT = "<|im_start|>assistant\n<think>\n\n</think>\n\n"

SYSTEM = (
    "You rewrite a hiker's weather question the way people type on a phone with one bar of signal.\n"
    "Rules:\n"
    "- Keep the meaning. Keep every time and number exactly as written, character for character.\n"
    "- Do not add any number, time or place.\n"
    "- One short line, under 90 characters. Lowercase, abbreviations and one small typo are fine.\n"
    "- Plain ASCII only. No emoji. Do not write words that contain digits, such as b4 or 2day.\n"
    "- Output only the rewritten question."
)

SHOTS = [
    ("storm before 3pm?", "any storm coming before 3pm"),
    ("how cold will it get?", "gonna be freezing up there?"),
    ("can I make it back to the car in time?", "will i get back down to the car ok"),
]


def messages(seed_question: str) -> list[dict]:
    out = [{"role": "system", "content": SYSTEM}]
    for src, dst in SHOTS:
        out += [{"role": "user", "content": src}, {"role": "assistant", "content": dst}]
    out.append({"role": "user", "content": seed_question})
    return out


def prompt(seed_question: str) -> str:
    """Few-shot turns are ordinary chat turns; only the final assistant turn opens with the empty think block."""
    msgs = messages(seed_question)
    return chatml(msgs[:-1])[: -len(_OPEN_ASSISTANT)] + chatml([msgs[-1]])


def _numbers(text: str) -> list[str]:
    return sorted(h.text.lower() for h in extract(text))


def clean(raw: str) -> str:
    lines = raw.strip().splitlines()
    text = lines[0].strip() if lines else ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def accept(seed_question: str, candidate: str) -> str | None:
    """The cleaned paraphrase if it is safe to use, else None."""
    text = clean(candidate)
    if not text or len(text) > MAX_CHARS:
        return None
    if not text.isascii() or re.search(r"[\x00-\x1f]", text):
        return None
    if _numbers(text) != _numbers(seed_question):
        return None
    if classify(text) != classify(seed_question):
        return None
    # The facts were computed from the seed. They hold a `target` fact only if the question names a clock time in a
    # form parse_target reads, so the paraphrase must read back as the same time (or none), or serving would
    # compute different facts from the paraphrase than the row stores.
    if parse_target(text) != parse_target(seed_question):
        return None
    return text
