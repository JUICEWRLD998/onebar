"""Teacher answers: a large open model writes candidates; only checker-passing, natural ones are kept.

The student's serving prompt (model.prompt.render) stays short. The teacher gets a richer prompt with worked examples,
because distillation only needs the teacher's output, not its prompt. Every example reply below passes the checker
against its own facts (a test enforces it), so the teacher is never shown a reply the checker would reject.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from onebar.check.checker import CheckResult, check
from onebar.facts.model import Fact, FactSet
from onebar.model.prompt import LABELS, SYSTEM, chatml, user_message

_OPEN_ASSISTANT = "<|im_start|>assistant\n<think>\n\n</think>\n\n"

TEACHER_SYSTEM = (
    SYSTEM
    + "\n- Write like a helpful friend texting back, in plain words. Never repeat a fact's name or label, only its value."
    + "\n- Put the answer first: yes, no, or the key fact."
    + "\n- For any go or no-go, safety, turn-around or 'can I' question, always also state the storm status and the strongest gust."
    + "\n- For a question about the daylight, rain, wind or temperature only, answer it and add at most one more fact."
    + "\n- If a storm starts at or before a time the hiker names, say so first."
)

# (question, [(key, token), ...], reply). Numbers differ from example to example on purpose.
EXAMPLES: list[tuple[str, list[tuple[str, str]], str]] = [
    (
        "storm before 3?",
        [("now", "10:20"), ("storm_first", "16:10"), ("gust_max", "48km/h"), ("gust_max_at", "17:00"),
         ("target", "15:00"), ("pop_max", "70%"), ("rain_first", "15:00")],
        "No storm before 15:00, but one starts at 16:10. Gusts up to 48km/h.",
    ),
    (
        "rain today?",
        [("now", "09:40"), ("rain_first", "17:00"), ("pop_max", "100%"), ("storm_none", "no storm")],
        "Yes. Rain from 17:00, chance up to 100%.",
    ),
    (
        "how windy is it going to get?",
        [("now", "11:05"), ("gust_max", "62km/h"), ("gust_max_at", "19:00"), ("storm_none", "no storm")],
        "Gusts up to 62km/h around 19:00.",
    ),
    (
        "do I need a headlamp?",
        [("now", "10:40"), ("sunset", "18:59"), ("daylight_left", "8h19m")],
        "Sunset is 18:59, so you have 8h19m of light. Bring one if you could be out near dusk.",
    ),
    (
        "is it safe to keep going?",
        [("now", "13:15"), ("storm_none", "no storm"), ("gust_max", "25km/h"), ("rain_none", "no rain")],
        "Looks OK. No storm expected, gusts up to 25km/h.",
    ),
    (
        "how cold will it get?",
        [("now", "08:30"), ("temp_now", "2C"), ("feels_min", "-5C"), ("storm_none", "no storm")],
        "2C now, feels like -5C at the coldest. Pack the warm jacket.",
    ),
    (
        "when do I need to turn around?",
        [("now", "10:50"), ("turn_by", "15:30"), ("car_by", "17:00"), ("storm_none", "no storm")],
        "Turn around by 15:30 to reach the car by 17:00. No storm expected.",
    ),
    (
        "wind, rain and temp for the next few hours?",
        [("now", "12:00"), ("gust_max", "41km/h"), ("rain_none", "no rain"), ("temp_now", "7C"),
         ("feels_min", "3C"), ("storm_none", "no storm")],
        "Gusts to 41km/h, no rain. 7C now and feeling like 3C at the lowest.",
    ),
]


def example_facts(pairs: list[tuple[str, str]]) -> FactSet:
    return FactSet(Fact(k, t) for k, t in pairs)


def messages(facts: FactSet, question: str) -> list[dict]:
    out = [{"role": "system", "content": TEACHER_SYSTEM}]
    for q, pairs, reply in EXAMPLES:
        out += [
            {"role": "user", "content": user_message(example_facts(pairs), q)},
            {"role": "assistant", "content": reply},
        ]
    out.append({"role": "user", "content": user_message(facts, question)})
    return out


def prompt(facts: FactSet, question: str) -> str:
    """Few-shot turns are ordinary chat turns; only the final assistant turn opens with the empty think block."""
    msgs = messages(facts, question)
    return chatml(msgs[:-1])[: -len(_OPEN_ASSISTANT)] + chatml([msgs[-1]])


_LABELS_LOW = {v.lower() for v in LABELS.values()}
_LONG_LABELS = sorted((p for p in _LABELS_LOW if len(p.split()) >= 3), key=len, reverse=True)
_LABEL_COLON = re.compile(r"(?:" + "|".join(re.escape(p) for p in sorted(_LABELS_LOW, key=len, reverse=True)) + r")\s*:")
_KEY = re.compile(r"\b[a-z]+_[a-z_]+\b")


def natural(text: str) -> bool:
    """False for replies that echo the facts block ("label: value", a long label, a key), or that are not one clean line.

    One-word labels such as "rain" or "light" are ordinary words, so they only count as an echo when followed by a colon.
    """
    low = text.lower()
    if "\n" in text or len(text) < 8:
        return False
    if _KEY.search(low) or _LABEL_COLON.search(low) or any(p in low for p in _LONG_LABELS):
        return False
    return True


@dataclass(frozen=True)
class Choice:
    text: str
    result: CheckResult
    n_candidates: int
    n_passed: int


def clean(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def pick(candidates: list[str], facts: FactSet, question: str) -> Choice | None:
    """The shortest candidate that passes the checker and reads naturally; ties go to the earliest."""
    seen: list[str] = []
    for raw in candidates:
        text = clean(raw)
        if text and text not in seen:
            seen.append(text)
    passed: list[tuple[str, CheckResult]] = []
    for text in seen:
        result = check(text, facts, question)
        if result.passed and natural(text):
            passed.append((text, result))
    if not passed:
        return None
    text, result = min(passed, key=lambda tr: tr[1].septets)
    return Choice(text, result, len(seen), len(passed))
