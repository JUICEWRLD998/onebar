"""Choose the channel by destination: web:<session> -> browser reply store, an email address -> SMTP, else the fallback."""
from __future__ import annotations


class RouterSender:
    """send(key, to, text) -> bool. Unknown destinations go to `fallback` (the local outbox) or are refused."""

    def __init__(self, email=None, web=None, fallback=None):
        self.email, self.web, self.fallback = email, web, fallback

    def send(self, key: str, to: str, text: str) -> bool:
        if to.startswith("web:"):
            return bool(self.web and self.web.send(key, to, text))
        if "@" in to and self.email is not None:
            return bool(self.email.send(key, to, text))
        if self.fallback is not None:
            return bool(self.fallback.send(key, to, text))
        return False
