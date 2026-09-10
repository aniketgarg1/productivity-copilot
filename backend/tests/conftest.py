"""Shared test fixtures.

Environment is configured before any `app.*` import because
`app.core.config.settings` and `app.db.session.engine` are both built at
import time.
"""

import os
import tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="copilot-tests-"), "test.db")

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DB}")
os.environ.setdefault("SESSION_SECRET", "test-secret-not-a-real-one")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DAILY_CHECKIN_ENABLED", "false")
os.environ.setdefault("TIMEZONE", "America/Phoenix")

import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import USER_COOKIE, user_serializer  # noqa: E402
from app.api.ratelimit import ALL_LIMITERS  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import GoogleToken, UserProfile  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

TEST_EMAIL = "tester@example.com"


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts from an empty schema."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Counters are process-global; without this, tests throttle each other."""
    for limiter in ALL_LIMITERS:
        limiter.reset()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def google_token_json(expiry: datetime | None = None) -> str:
    return json.dumps(
        {
            "token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "scopes": [],
            "expiry": expiry.isoformat() if expiry else None,
        }
    )


@pytest.fixture
def connected_user(db):
    """A user with a Google token and a profile, as if OAuth had completed."""
    db.add(GoogleToken(
        email=TEST_EMAIL,
        token_json=google_token_json(datetime.now(timezone.utc) + timedelta(hours=1)),
    ))
    profile = UserProfile(email=TEST_EMAIL, name="Tester", timezone="America/Phoenix")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@pytest.fixture
def client():
    """Unauthenticated client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client():
    """Client carrying a validly signed session cookie."""
    with TestClient(app) as c:
        c.cookies.set(USER_COOKIE, user_serializer().dumps({"email": TEST_EMAIL}))
        yield c


class FakeLLM:
    """Stand-in for the OpenAI provider. Records what it was asked."""

    def __init__(self, json_result=None, text_result="fake reply"):
        self.json_result = json_result if json_result is not None else {}
        self.text_result = text_result
        self.calls = []

    async def generate_json(self, **kwargs):
        self.calls.append(("json", kwargs))
        return self.json_result

    async def generate_text(self, **kwargs):
        self.calls.append(("text", kwargs))
        return self.text_result


def roadmap_fixture() -> dict:
    """A roadmap that deliberately repeats a task title across milestones."""
    return {
        "goal": "Learn Rust",
        "time_horizon_days": 14,
        "milestones": [
            {
                "title": "Ownership",
                "why_it_matters": "Everything downstream depends on it",
                "due_in_days": 4,
                "tasks": [
                    {
                        "title": "Read the Book ch. 4",
                        "estimate_minutes": 45,
                        "difficulty": "easy",
                        "notes": "Take notes",
                        "resources": [
                            {"title": "The Book", "url": "https://doc.rust-lang.org/book/", "type": "docs"}
                        ],
                    },
                    {
                        "title": "Exercism exercises",
                        "estimate_minutes": 60,
                        "difficulty": "medium",
                        "notes": "",
                        "resources": [],
                    },
                ],
            },
            {
                "title": "Ship something",
                "why_it_matters": "Reading is not writing",
                "due_in_days": 14,
                "tasks": [
                    {
                        # Same title as the first milestone's task on purpose:
                        # this used to collide on the unique task_hash.
                        "title": "Read the Book ch. 4",
                        "estimate_minutes": 45,
                        "difficulty": "hard",
                        "notes": "",
                        "resources": [],
                    },
                    {
                        # Longer than a 2h/day budget: used to be dropped silently.
                        "title": "Build the whole CLI",
                        "estimate_minutes": 300,
                        "difficulty": "hard",
                        "notes": "",
                        "resources": [],
                    },
                ],
            },
        ],
    }
