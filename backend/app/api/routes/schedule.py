from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.db.session import get_db
from app.db.models import GoogleToken
from app.llm.factory import get_llm
from app.agents.planner import make_roadmap
from app.agents.scheduler import flatten_tasks, build_free_slots, schedule_tasks_into_slots
from app.tools.google_calendar import freebusy, create_event
from app.schemas.roadmap import ScheduleResponse

router = APIRouter(prefix="/goals")


class ScheduleRequest(BaseModel):
    goal: str = Field(..., min_length=3, max_length=1000)
    horizon_days: int = Field(30, ge=1, le=365)
    holidays: list[str] = Field(default_factory=list)  # ["2026-03-10", ...]


def _get_token(db: Session) -> GoogleToken:
    # Always use most recently connected account (prevents stale-token 403s)
    tok = db.query(GoogleToken).order_by(desc(GoogleToken.id)).first()
    if not tok:
        raise HTTPException(status_code=400, detail="No Google account connected. Use /auth/google/start")
    return tok


@router.post("/schedule", response_model=ScheduleResponse)
async def schedule_goal(req: ScheduleRequest, db: Session = Depends(get_db)):
    tok = _get_token(db)

    llm = get_llm()
    roadmap = await make_roadmap(llm, req.goal, req.horizon_days)

    tasks = flatten_tasks(roadmap)
    if not tasks:
        raise HTTPException(status_code=400, detail="No tasks generated")

    free_slots = build_free_slots(
        freebusy_func=freebusy,
        token_json=tok.token_json,
        horizon_days=req.horizon_days,
        timezone=settings.TIMEZONE,
        holidays=req.holidays,
    )

    scheduled = schedule_tasks_into_slots(tasks, free_slots, settings.TIMEZONE)

    if not scheduled:
        return {"message": "No available slots found in horizon.", "roadmap": roadmap, "events": []}

    events = []
    for s in scheduled:
        ev = create_event(
            token_json=tok.token_json,
            summary=f"🧠 Task: {s['title']}",
            description=s.get("notes") or "",
            start_dt=s["start"],
            end_dt=s["end"],
            timezone=settings.TIMEZONE,
        )
        events.append({**ev, "title": s["title"], "start": s["start"].isoformat(), "end": s["end"].isoformat()})

    return {"roadmap": roadmap, "events": events}