from fastapi import FastAPI

from app.db.base import Base
from app.db.session import engine
from app.api.routes.google_auth import router as google_auth_router
from app.api.routes.calendar import router as calendar_router
from app.api.routes.goals import router as goals_router
from app.api.routes.schedule import router as schedule_router
app = FastAPI(title="Productivity Copilot API")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(google_auth_router, tags=["auth"])
app.include_router(calendar_router, tags=["calendar"])
app.include_router(goals_router, tags=["goals"])
app.include_router(schedule_router, tags=["schedule"])