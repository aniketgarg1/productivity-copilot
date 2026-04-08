import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Productivity Copilot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(google_auth_router, tags=["auth"])
app.include_router(calendar_router, tags=["calendar"])
app.include_router(goals_router, tags=["goals"])
app.include_router(schedule_router, tags=["schedule"])
app.include_router(voice_router, tags=["voice"])
app.include_router(tasks_router, tags=["tasks"])
app.include_router(calls_router, tags=["calls"])
app.include_router(chat_router, tags=["chat"])
app.include_router(analytics_router, tags=["analytics"])