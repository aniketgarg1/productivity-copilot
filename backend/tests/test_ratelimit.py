"""Per-user throttling on the endpoints that cost money."""

from unittest.mock import patch

import pytest

from app.api.ratelimit import RateLimiter, chat_limiter
from tests.conftest import FakeLLM


class TestRateLimiter:
    def test_allows_up_to_the_limit(self):
        limiter = RateLimiter(limit=3, window_seconds=60, name="test")
        for _ in range(3):
            limiter.check("user@example.com")

    def test_blocks_past_the_limit(self):
        from fastapi import HTTPException

        limiter = RateLimiter(limit=2, window_seconds=60, name="test")
        limiter.check("user@example.com")
        limiter.check("user@example.com")

        with pytest.raises(HTTPException) as exc:
            limiter.check("user@example.com")

        assert exc.value.status_code == 429
        assert "Retry-After" in exc.value.headers

    def test_users_are_counted_separately(self):
        limiter = RateLimiter(limit=1, window_seconds=60, name="test")
        limiter.check("a@example.com")
        limiter.check("b@example.com")  # must not raise

    def test_the_window_rolls_off(self, monkeypatch):
        import app.api.ratelimit as rl

        clock = {"t": 1000.0}
        monkeypatch.setattr(rl.time, "monotonic", lambda: clock["t"])

        limiter = RateLimiter(limit=1, window_seconds=60, name="test")
        limiter.check("user@example.com")

        clock["t"] += 61
        limiter.check("user@example.com")  # must not raise


class TestChatEndpointIsThrottled:
    def test_returns_429_once_the_limit_is_hit(self, auth_client, connected_user):
        with patch("app.api.routes.chat.get_llm", lambda: FakeLLM()):
            statuses = [
                auth_client.post("/chat", json={"message": "hi"}).status_code
                for _ in range(chat_limiter.limit + 2)
            ]

        assert statuses[0] == 200
        assert statuses[-1] == 429
        assert statuses.count(200) == chat_limiter.limit

    def test_throttling_happens_before_any_model_call(self, auth_client, connected_user):
        llm = FakeLLM()
        with patch("app.api.routes.chat.get_llm", lambda: llm):
            for _ in range(chat_limiter.limit + 3):
                auth_client.post("/chat", json={"message": "hi"})

        # The throttled requests must not have reached the (billed) model.
        assert len(llm.calls) == chat_limiter.limit

    def test_an_unauthenticated_request_is_rejected_not_counted(self, client):
        assert client.post("/chat", json={"message": "hi"}).status_code == 401
