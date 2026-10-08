"""GSM 03.38 septet counting for one SMS.

The text is checked exactly as given. Callers must normalise (NFC) before sending, because a
combining accent is not a GSM character and is rejected here rather than silently fixed.
"""
from __future__ import annotations

from dataclasses import dataclass

LIMIT = 160

# Basic character set (GSM 03.38), without the ESC code point. One septet each.
BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅå"
    "Δ_ΦΓΛΩΠΨΣΘΞ"
    "ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# Extension table (reached through ESC). Two septets each. Form feed is left out on purpose.
EXTENSION = frozenset("^{}\\[~]|€")


@dataclass(frozen=True)
class Gsm7Result:
    septets: int
    bad_chars: tuple[str, ...]

    @property
    def fits(self) -> bool:
        return not self.bad_chars and self.septets <= LIMIT


def analyze(text: str) -> Gsm7Result:
    count = 0
    bad: list[str] = []
    for ch in text:
        if ch in BASIC:
            count += 1
        elif ch in EXTENSION:
            count += 2
        elif ch not in bad:
            bad.append(ch)
    return Gsm7Result(septets=count, bad_chars=tuple(bad))


def septets(text: str) -> int:
    """Septet count. Characters outside GSM-7 are not counted; use analyze() to see them."""
    return analyze(text).septets
