import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.api.routes.google_auth import router as google_auth_router
from app.api.routes.calendar import router as calendar_router
from app.api.routes.goals import router as goals_router
from app.api.routes.schedule import router as schedule_router
from app.api.routes.voice import router as voice_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.calls import router as calls_router
from app.api.routes.chat import router as chat_router
from app.api.routes.analytics import router as analytics_router
from app.jobs.daily_checkin import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _create_tables(attempts: int = 10, delay: float = 2.0) -> None:
    """Postgres often isn't accepting connections yet when the API container starts."""
    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError:
            if attempt == attempts:
                raise
            logger.warning("Database not ready (attempt %s/%s), retrying…", attempt, attempts)
            time.sleep(delay)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.SESSION_SECRET in ("change-me", "change-this-to-any-random-string"):
        logger.warning(
            "SESSION_SECRET is still the default value — session cookies are forgeable. "
            "Set SESSION_SECRET in .env (e.g. `python -c \"import secrets;print(secrets.token_urlsafe(32))\"`)."
        )
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set — planning, chat and voice endpoints will fail.")
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        logger.warning("Google OAuth is not configured — calendar features will fail.")

    _create_tables()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Productivity Copilot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config-check")
def config_check():
    """Which integrations are configured. Never returns secret values."""
    return {
        "google_oauth": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "google_redirect_uri": settings.google_redirect_uri,
        "openai": bool(settings.OPENAI_API_KEY),
        "twilio": bool(
            settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_PHONE_NUMBER
        ),
        "twilio_webhooks_reachable": settings.backend_is_public,
        "session_secret_is_default": settings.SESSION_SECRET in ("change-me", "change-this-to-any-random-string"),
        "daily_checkin_enabled": settings.DAILY_CHECKIN_ENABLED,
        "timezone": settings.TIMEZONE,
        "cors_origins": settings.cors_origins,
    }


app.include_router(google_auth_router, tags=["auth"])
app.include_router(calendar_router, tags=["calendar"])
app.include_router(goals_router, tags=["goals"])
app.include_router(schedule_router, tags=["schedule"])
app.include_router(voice_router, tags=["voice"])
app.include_router(tasks_router, tags=["tasks"])
app.include_router(calls_router, tags=["calls"])
app.include_router(chat_router, tags=["chat"])
app.include_router(analytics_router, tags=["analytics"])
