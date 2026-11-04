"""In-process token-bucket rate limiter, one bucket per API key (P6d).

Single-process only (fine for the SQLite / one-worker set-up); a multi-worker
deployment would need a shared store. Defaults come from LOGIMIND_RATE_PER_MIN
(default 60 requests/minute) and LOGIMIND_RATE_BURST (default 20).
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable


class RateLimiter:
    def __init__(self, per_minute: float | None = None, burst: int | None = None,
                 clock: Callable[[], float] = time.monotonic):
        per_minute = per_minute if per_minute is not None else float(os.environ.get("LOGIMIND_RATE_PER_MIN", "60"))
        self.rate = per_minute / 60
        self.burst = burst if burst is not None else int(os.environ.get("LOGIMIND_RATE_BURST", "20"))
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """(allowed, seconds until the next token if refused)."""
        now = self.clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.burst), now))
            tokens = min(float(self.burst), tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            return False, (1.0 - tokens) / self.rate if self.rate > 0 else float("inf")
