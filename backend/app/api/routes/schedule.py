from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from itsdangerous import URLSafeSerializer

import hashlib
from datetime import datetime, timedelta

from app.core.config import settings
from app.db.session import get_db
from app.db.models import GoogleToken, UserProfile, TaskRecord
from app.llm.factory import get_llm
from app.agents.planner import make_roadmap
from app.agents.scheduler import flatten_tasks, build_free_slots, schedule_tasks_into_slots
from app.tools.google_calendar import freebusy, create_event, list_events, _refresh_and_persist, updated_token_json
from app.schemas.roadmap import ScheduleResponse

router = APIRouter(prefix="/goals")


def _user_serializer():
    return URLSafeSerializer(settings.SESSION_SECRET, salt="pc-user-session")


def _task_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _as_dict(obj):
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    # Pydantic v1
    if hasattr(obj, "dict"):
        return obj.dict()
    # dataclass / plain object
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    # already a dict (or close enough)
    return obj


class ScheduleRequest(BaseModel):
    goal: str = Field(..., min_length=3, max_length=1000)
    horizon_days: int = Field(30, ge=1, le=365)
    holidays: list[str] = Field(default_factory=list)
    context: str = Field("", max_length=5000, description="Background context from intake conversation")
    daily_hours: float = Field(2.0, ge=0.5, le=12, description="Max hours per day to dedicate to tasks")


def _get_current_email(request: Request) -> str:
    cookie = request.cookies.get("pc_user")
    if not cookie:
        raise HTTPException(status_code=401, detail="Not authenticated. Connect Google at /auth/google/start")
    try:
        data = _user_serializer().loads(cookie)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session. Reconnect Google at /auth/google/start")

    email = data.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing user session. Reconnect Google at /auth/google/start")

    return email


def _get_token(db: Session, email: str) -> GoogleToken:
    tok = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    if not tok:
        raise HTTPException(status_code=401, detail="No Google account connected for this user. Use /auth/google/start")
    return tok


@router.post("/schedule", response_model=ScheduleResponse)
async def schedule_goal(req: ScheduleRequest, request: Request, db: Session = Depends(get_db)):
    email = _get_current_email(request)
    tok = _get_token(db, email)

    # Auto-refresh expired Google tokens and persist the new token
    creds, refreshed = _refresh_and_persist(tok.token_json)
    if refreshed:
        tok.token_json = updated_token_json(creds)
        db.commit()

    llm = get_llm()
    roadmap = await make_roadmap(llm, req.goal, req.horizon_days, context=req.context)

    tasks = flatten_tasks(roadmap)
    if not tasks:
        raise HTTPException(status_code=400, detail="No tasks generated")

    # Attach stable task_id to each Task object (keep objects; scheduler expects .minutes)
    for t in tasks:
        title = getattr(t, "title", "")
        milestone_title = getattr(t, "milestone_title", "")
        minutes = getattr(t, "minutes", None)

        seed = f"{req.goal}|{milestone_title}|{title}|{minutes}"
        setattr(t, "task_id", _task_id(seed))

    # Build mapping so we can attach task_id back onto scheduled dicts later
    task_id_by_title = {getattr(t, "title", ""): getattr(t, "task_id", None) for t in tasks}

    free_slots = build_free_slots(
        freebusy_func=freebusy,
        token_json=tok.token_json,
        horizon_days=req.horizon_days,
        timezone=settings.TIMEZONE,
        holidays=req.holidays,
    )

    max_daily_minutes = int(req.daily_hours * 60)
    scheduled = schedule_tasks_into_slots(tasks, free_slots, settings.TIMEZONE, max_daily_minutes=max_daily_minutes)
    if not scheduled:
        return {"message": "No available slots found in horizon.", "roadmap": roadmap, "events": []}

    # Convert scheduled items to dicts (scheduler returns dicts or models depending on implementation)
    scheduled = [_as_dict(s) for s in scheduled]

    # Ensure task_id exists on scheduled items (if scheduler didn’t carry it through)
    for s in scheduled:
        if isinstance(s, dict) and not s.get("task_id"):
            s["task_id"] = task_id_by_title.get(s.get("title", ""))

    # Fetch existing Copilot task_ids already scheduled in this horizon
    now = datetime.now().astimezone()
    time_min = now.isoformat()
    time_max = (now + timedelta(days=req.horizon_days)).isoformat()

    existing_events = list_events(tok.token_json, time_min, time_max)
    existing_task_ids = set()
    for ev in existing_events:
        ext = (ev.get("extendedProperties") or {}).get("private") or {}
        tid = ext.get("productivity_copilot_task_id")
        if tid:
            existing_task_ids.add(tid)

    # Ensure user profile exists for task tracking
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        profile = UserProfile(email=email)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    events = []
    for s in scheduled:
        tid = s.get("task_id")
        if tid and tid in existing_task_ids:
            continue

        # Build rich description with notes and resource links
        desc_parts = []
        if s.get("notes"):
            desc_parts.append(s["notes"])
        resources = s.get("resources") or []
        if resources:
            desc_parts.append("\nResources:")
            for r in resources:
                desc_parts.append(f"- {r.get('title', '')}: {r.get('url', '')}")
        description = "\n".join(desc_parts)

        ev = create_event(
            token_json=tok.token_json,
            summary=f"🧠 Task: {s['title']}",
            description=description,
            start_dt=s["start"],
            end_dt=s["end"],
            timezone=settings.TIMEZONE,
            task_id=tid,
        )

        # Persist task for progress tracking / daily check-in calls
        task_record = TaskRecord(
            user_id=profile.id,
            goal=req.goal,
            title=s["title"],
            notes=s.get("notes"),
            estimate_minutes=int((s["end"] - s["start"]).total_seconds() / 60),
            scheduled_start=s["start"],
            scheduled_end=s["end"],
            calendar_event_id=ev.get("id"),
            resources_json=resources,
            task_hash=tid,
            status="pending",
        )
        db.add(task_record)

        events.append(
            {
                **ev,
                "task_id": tid,
                "title": s["title"],
                "start": s["start"].isoformat(),
                "end": s["end"].isoformat(),
            }
        )

    db.commit()
    return {"roadmap": roadmap, "events": events}