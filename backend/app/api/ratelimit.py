"""A small per-user rate limiter for the endpoints that cost money.

Planning, chat and transcription each spend OpenAI credits (and scheduling also
writes to the user's calendar), so an accidental retry loop in a frontend is
expensive. This is an in-process fixed-window counter: it is per-worker, not
cluster-wide, which is the right trade for a single-container deploy. Move to
Redis if you ever run more than one instance.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.api.deps import get_current_email


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int, name: str):
        self.limit = limit
        self.window = window_seconds
        self.name = name
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._hits[key] if now - t < self.window]
        self._hits[key] = recent
        return recent

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = self._prune(key, now)
            if len(recent) >= self.limit:
                retry_after = int(self.window - (now - recent[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Rate limit reached for {self.name}: {self.limit} requests "
                        f"per {self.window}s. Try again in {retry_after}s."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            self._hits[key].append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def dependency(self):
        """FastAPI dependency that keys the limit on the signed-in user."""

        async def _check(request: Request) -> None:
            self.check(get_current_email(request))

        return _check


# Planning and scheduling: a full roadmap generation plus calendar writes.
planning_limiter = RateLimiter(limit=10, window_seconds=300, name="goal planning")
# Chat is cheap per call but easy to loop.
chat_limiter = RateLimiter(limit=30, window_seconds=60, name="chat")
# Whisper is billed per minute of audio.
transcription_limiter = RateLimiter(limit=15, window_seconds=300, name="transcription")
# Outbound phone calls cost money and ring a real phone.
call_limiter = RateLimiter(limit=3, window_seconds=600, name="check-in calls")

ALL_LIMITERS = (planning_limiter, chat_limiter, transcription_limiter, call_limiter)
