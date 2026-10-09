"""Per-sender sliding-window rate limit. In memory; the limit protects the model budget and the inbox, not accounts."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable


class RateLimiter:
    def __init__(self, max_events: int = 10, window_s: float = 600.0, clock: Callable[[], float] = time.monotonic):
        self.max_events, self.window_s, self.clock = max_events, window_s, clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """True and counts the event, or False when `key` has used its allowance in the window."""
        now = self.clock()
        with self._lock:
            q = self._events[key]
            while q and now - q[0] >= self.window_s:
                q.popleft()
            if len(q) >= self.max_events:
                return False
            q.append(now)
            return True
