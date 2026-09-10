import hashlib
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_email, get_google_token
from app.core.config import settings
from app.db.session import get_db
from app.db.models import UserProfile, TaskRecord
from app.llm.factory import get_llm
from app.agents.planner import make_roadmap
from app.agents.scheduler import flatten_tasks, build_free_slots, schedule_tasks_into_slots
from app.tools.google_calendar import (
    build_calendar_service,
    create_event,
    ensure_fresh_token,
    freebusy,
    list_events,
)
from app.schemas.roadmap import Roadmap, ScheduleResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goals")


def _task_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class ScheduleRequest(BaseModel):
    goal: str = Field(..., min_length=3, max_length=1000)
    horizon_days: int = Field(30, ge=1, le=365)
    holidays: list[str] = Field(default_factory=list)
    context: str = Field("", max_length=5000, description="Background context from intake conversation")
    daily_hours: float = Field(2.0, ge=0.5, le=12, description="Max hours per day to dedicate to tasks")


@router.post("/schedule", response_model=ScheduleResponse)
async def schedule_goal(req: ScheduleRequest, request: Request, db: Session = Depends(get_db)):
    email = get_current_email(request)
    tok = get_google_token(db, email)

    # Refresh the Google token once up front and persist it, so later calls in
    # this request (and subsequent requests) reuse a valid access token.
    token_json = ensure_fresh_token(db, tok)

    llm = get_llm()
    roadmap = await make_roadmap(llm, req.goal, req.horizon_days, context=req.context)

    # Fail loudly here rather than as an opaque response-validation 500 later.
    try:
        Roadmap.model_validate(roadmap)
    except ValidationError as exc:
        logger.error("Model produced an invalid roadmap: %s", exc)
        raise HTTPException(status_code=502, detail="The AI returned an unusable roadmap. Please try again.")

    tasks = flatten_tasks(roadmap)
    if not tasks:
        raise HTTPException(status_code=400, detail="No tasks generated")

    # Stable per-task id. The milestone title and position are part of the seed
    # because roadmaps legitimately repeat a task title across milestones, and
    # colliding ids used to blow up on the unique task_hash constraint.
    for t in tasks:
        t.task_id = _task_id(f"{req.goal}|{t.milestone_title}|{t.title}|{t.index}|{t.minutes}")

    free_slots = build_free_slots(
        freebusy_func=freebusy,
        token_json=token_json,
        horizon_days=req.horizon_days,
        timezone=settings.TIMEZONE,
        holidays=req.holidays,
    )

    max_daily_minutes = int(req.daily_hours * 60)
    scheduled, unscheduled = schedule_tasks_into_slots(
        tasks, free_slots, settings.TIMEZONE, max_daily_minutes=max_daily_minutes
    )
    if not scheduled:
        return {"message": "No available slots found in horizon.", "roadmap": roadmap, "events": []}

    # One Calendar client for the whole batch instead of one per event.
    service = build_calendar_service(token_json)

    now = datetime.now().astimezone()
    existing_events = list_events(
        now.isoformat(),
        (now + timedelta(days=req.horizon_days)).isoformat(),
        service=service,
    )
    existing_task_ids = set()
    for ev in existing_events:
        ext = (ev.get("extendedProperties") or {}).get("private") or {}
        tid = ext.get("productivity_copilot_task_id")
        if tid:
            existing_task_ids.add(tid)

    # Tasks already stored from a previous run must be skipped too, otherwise
    # the unique task_hash constraint aborts the whole transaction.
    scheduled_ids = [s["task_id"] for s in scheduled if s.get("task_id")]
    if scheduled_ids:
        existing_task_ids.update(
            row[0]
            for row in db.query(TaskRecord.task_hash)
            .filter(TaskRecord.task_hash.in_(scheduled_ids))
            .all()
        )

    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        profile = UserProfile(email=email)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    events = []
    skipped = 0
    seen_in_batch: set[str] = set()

    for s in scheduled:
        tid = s.get("task_id")
        if tid and (tid in existing_task_ids or tid in seen_in_batch):
            skipped += 1
            continue
        if tid:
            seen_in_batch.add(tid)

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

        try:
            ev = create_event(
                summary=f"🧠 Task: {s['title']}",
                description=description,
                start_dt=s["start"],
                end_dt=s["end"],
                timezone_name=settings.TIMEZONE,
                task_id=tid,
                service=service,
            )
        except Exception:
            # Don't abandon the rest of the plan because one insert failed.
            logger.exception("Failed to create calendar event for task %r", s.get("title"))
            skipped += 1
            continue

        db.add(
            TaskRecord(
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
        )

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

    parts = [f"Scheduled {len(events)} task(s)."]
    if skipped:
        parts.append(f"{skipped} already scheduled or skipped.")
    if unscheduled:
        parts.append(
            f"{len(unscheduled)} task(s) did not fit in the next {req.horizon_days} days "
            f"at {req.daily_hours}h/day — extend the horizon or raise the daily budget."
        )

    return {"roadmap": roadmap, "events": events, "message": " ".join(parts)}
