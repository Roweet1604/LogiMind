"""Copilot limits for a public server (decision 0046): anyone with the demo link uses the server's hosted model key,
so model calls are capped per client IP, per chat session, for the whole server per minute and per day, and
messages have a maximum length. Separate from the per-API-key limiter (all demo visitors share one key).

Settings (0 switches a limit off). Defaults: on in the public demo (LOGIMIND_PUBLIC_DEMO=1), off elsewhere.
  LOGIMIND_COPILOT_PER_CLIENT_PER_MIN  messages per minute per client IP and per session   public 5, else 0
  LOGIMIND_COPILOT_PER_MIN             messages per minute for the whole server            public 12, else 0
  LOGIMIND_COPILOT_PER_DAY             messages per UTC day for the whole server           public 300, else 0
  LOGIMIND_COPILOT_MAX_CHARS           longest message                                    public 500, else 2000
In-process only (one uvicorn worker, like the main limiter).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from fastapi import HTTPException, Request

from app.services.ratelimit import RateLimiter

PUBLIC_DEFAULTS = {"per_client": 5, "per_min": 12, "per_day": 300, "max_chars": 500}
PRIVATE_DEFAULTS = {"per_client": 0, "per_min": 0, "per_day": 0, "max_chars": 2000}
ENV = {"per_client": "LOGIMIND_COPILOT_PER_CLIENT_PER_MIN", "per_min": "LOGIMIND_COPILOT_PER_MIN",
       "per_day": "LOGIMIND_COPILOT_PER_DAY", "max_chars": "LOGIMIND_COPILOT_MAX_CHARS"}


def client_ip(request: Request) -> str:
    """The caller's address. Behind the host's proxies (private addresses) the right-most public address in
    X-Forwarded-For is the one the outermost proxy saw; entries left of it can be typed by the caller."""
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    for hop in reversed(hops):
        try:
            ip = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if ip.is_global:
            return str(ip)
    return request.client.host if request.client else "unknown"


def utc_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


@dataclass
class DailyCounter:
    limit: int
    clock: Callable[[], dt.date] = utc_today
    _day: dt.date | None = None
    _used: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self) -> bool:
        with self._lock:
            today = self.clock()
            if today != self._day:
                self._day, self._used = today, 0
            if self._used >= self.limit:
                return False
            self._used += 1
            return True


class CopilotLimits:
    def __init__(self, per_client: int, per_min: int, per_day: int, max_chars: int,
                 clock: Callable[[], float] = time.monotonic, day_clock: Callable[[], dt.date] | None = None):
        self.max_chars = max_chars
        # a bucket holds up to half a minute's messages, at least 1: a burst cannot use a whole minute at once
        self.per_client = RateLimiter(per_client, max(1, per_client // 2), clock) if per_client > 0 else None
        self.overall = RateLimiter(per_min, max(1, per_min // 2), clock) if per_min > 0 else None
        self.daily = DailyCounter(per_day, day_clock or utc_today) if per_day > 0 else None

    @classmethod
    def from_env(cls, public: bool, env: dict[str, str] | None = None) -> CopilotLimits:
        env = os.environ if env is None else env
        defaults = PUBLIC_DEFAULTS if public else PRIVATE_DEFAULTS
        values = {}
        for name, var in ENV.items():
            raw = env.get(var, "").strip()
            values[name] = int(raw) if raw.isdigit() else defaults[name]
        return cls(**values)

    def describe(self) -> dict:
        return {"max_message_chars": self.max_chars}

    def check_length(self, message: str) -> None:
        if self.max_chars > 0 and len(message) > self.max_chars:
            raise HTTPException(400, detail=f"Messages to the copilot are limited to {self.max_chars} characters on "
                                            "this server. Please shorten it.")

    def take(self, request: Request, session_id: str | None = None) -> None:
        """Count one model call for this caller, or refuse it with 429 and a plain reason."""
        if self.per_client:
            keys = [f"ip:{client_ip(request)}"] + ([f"session:{session_id}"] if session_id else [])
            for key in keys:
                ok, wait = self.per_client.check(key)
                if not ok:
                    self._refuse("You are sending copilot messages too quickly", wait)
        if self.overall:
            ok, wait = self.overall.check("all")
            if not ok:
                self._refuse("The copilot is busy: this public demo allows only a few messages per minute in total",
                             wait)
        if self.daily and not self.daily.take():
            raise HTTPException(429, detail="The copilot has reached today's message limit for this public demo. "
                                            "Plans and replans still work from the Plans page.")

    @staticmethod
    def _refuse(what: str, wait: float) -> None:
        secs = max(1, math.ceil(wait))
        raise HTTPException(429, detail=f"{what}. Try again in {secs} s. Plans and replans still work from the "
                                        "Plans page.", headers={"Retry-After": str(secs)})
