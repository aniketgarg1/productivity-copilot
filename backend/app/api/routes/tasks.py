"""Task progress tracking — view, update status, and manage tasks."""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.agents.calendar_sync import reconcile, sync_window
from app.api.deps import get_current_email, get_google_token
from app.core.config import settings
from app.db.session import get_db
from app.db.models import UserProfile, TaskRecord
from app.tools.google_calendar import (
    delete_event,
    ensure_fresh_token,
    list_events,
    update_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks")


class TaskStatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "done", "skipped"]
    progress_note: str | None = None


class TaskReschedule(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class PhoneRegistration(BaseModel):
    phone: str = Field(..., min_length=10, max_length=20, description="E.164 format, e.g. +14155551234")
    name: str | None = None
    daily_checkin_enabled: bool = True
    preferred_checkin_hour: int = Field(9, ge=0, le=23)
    timezone: str = "America/Phoenix"


@router.get("")
async def list_tasks(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
):
    """List all tasks for the current user, optionally filtered by status."""
    email = get_current_email(request)
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        return {"tasks": []}

    q = db.query(TaskRecord).filter(TaskRecord.user_id == profile.id)
    if status:
        q = q.filter(TaskRecord.status == status)

    tasks = q.order_by(TaskRecord.scheduled_start).all()
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "goal": t.goal,
                "notes": t.notes,
                "estimate_minutes": t.estimate_minutes,
                "scheduled_start": t.scheduled_start.isoformat() if t.scheduled_start else None,
                "scheduled_end": t.scheduled_end.isoformat() if t.scheduled_end else None,
                "calendar_event_id": t.calendar_event_id,
                "status": t.status,
                "progress_note": t.progress_note,
                "resources": t.resources_json or [],
                "last_synced_at": t.last_synced_at.isoformat() if t.last_synced_at else None,
            }
            for t in tasks
        ]
    }


def _owned_task(db: Session, request: Request, task_id: int) -> tuple[TaskRecord, UserProfile]:
    email = get_current_email(request)
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    task = (
        db.query(TaskRecord)
        .filter(TaskRecord.id == task_id, TaskRecord.user_id == profile.id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task, profile


@router.post("/sync")
async def sync_with_calendar(request: Request, db: Session = Depends(get_db)):
    """
    Reconcile stored tasks against Google Calendar.

    Moving or deleting an event in Google is invisible to the app otherwise —
    scheduled times go stale and check-in calls cite the wrong hour.
    """
    email = get_current_email(request)
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        return {"checked": 0, "unchanged": 0, "moved": [], "removed": [],
                "skipped_no_event": 0, "summary": "No tasks to check."}

    token_json = ensure_fresh_token(db, get_google_token(db, email))

    tasks = (
        db.query(TaskRecord)
        .filter(TaskRecord.user_id == profile.id, TaskRecord.calendar_event_id.isnot(None))
        .all()
    )
    window = sync_window(tasks)
    if not window:
        return {"checked": 0, "unchanged": 0, "moved": [], "removed": [],
                "skipped_no_event": len(tasks), "summary": "No scheduled tasks to check."}

    start, end = window
    events = list_events(start.isoformat() + "Z", end.isoformat() + "Z", token_json=token_json)
    return reconcile(db, tasks, events).as_dict()


@router.patch("/{task_id}/reschedule")
async def reschedule_task(
    task_id: int,
    body: TaskReschedule,
    request: Request,
    db: Session = Depends(get_db),
):
    """Move a task to a new time, updating Google Calendar to match."""
    task, _ = _owned_task(db, request, task_id)
    email = get_current_email(request)

    if task.calendar_event_id:
        token_json = ensure_fresh_token(db, get_google_token(db, email))
        try:
            update_event(
                task.calendar_event_id,
                body.start,
                body.end,
                settings.TIMEZONE,
                token_json=token_json,
            )
        except Exception as exc:
            # Don't record a time the calendar doesn't actually have.
            logger.exception("Failed to move calendar event for task %s", task_id)
            raise HTTPException(status_code=502, detail=f"Could not update the calendar event: {exc}")

    task.scheduled_start = body.start.replace(tzinfo=None) if body.start.tzinfo else body.start
    task.scheduled_end = body.end.replace(tzinfo=None) if body.end.tzinfo else body.end
    task.estimate_minutes = max(1, int((body.end - body.start).total_seconds() // 60))
    task.last_synced_at = datetime.utcnow()
    db.commit()

    return {
        "id": task.id,
        "title": task.title,
        "scheduled_start": task.scheduled_start.isoformat(),
        "scheduled_end": task.scheduled_end.isoformat(),
        "estimate_minutes": task.estimate_minutes,
    }


@router.delete("/{task_id}")
async def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a task and remove its calendar event."""
    task, _ = _owned_task(db, request, task_id)
    email = get_current_email(request)

    calendar_event_removed = False
    if task.calendar_event_id:
        try:
            token_json = ensure_fresh_token(db, get_google_token(db, email))
            calendar_event_removed = delete_event(
                task.calendar_event_id, token_json=token_json
            )
        except HTTPException:
            raise
        except Exception:
            # The row still goes; a stranded event is better than a stuck task.
            logger.exception("Failed to delete calendar event for task %s", task_id)

    db.delete(task)
    db.commit()

    return {
        "deleted": task_id,
        "calendar_event_removed": calendar_event_removed,
    }


@router.patch("/{task_id}")
async def update_task_status(
    task_id: int,
    body: TaskStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update the status of a task (pending, in_progress, done, skipped)."""
    email = get_current_email(request)
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    task = db.query(TaskRecord).filter(
        TaskRecord.id == task_id,
        TaskRecord.user_id == profile.id,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = body.status
    if body.progress_note is not None:
        task.progress_note = body.progress_note
    db.commit()

    return {"id": task.id, "title": task.title, "status": task.status}


@router.post("/register-phone")
async def register_phone(
    body: PhoneRegistration,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register or update the user's phone number for daily check-in calls."""
    email = get_current_email(request)

    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if profile:
        profile.phone = body.phone
        if body.name:
            profile.name = body.name
        profile.daily_checkin_enabled = body.daily_checkin_enabled
        profile.preferred_checkin_hour = body.preferred_checkin_hour
        profile.timezone = body.timezone
    else:
        profile = UserProfile(
            email=email,
            phone=body.phone,
            name=body.name,
            daily_checkin_enabled=body.daily_checkin_enabled,
            preferred_checkin_hour=body.preferred_checkin_hour,
            timezone=body.timezone,
        )
        db.add(profile)

    db.commit()
    return {
        "message": "Phone registered for daily check-ins",
        "phone": profile.phone,
        "daily_checkin_enabled": profile.daily_checkin_enabled,
        "preferred_checkin_hour": profile.preferred_checkin_hour,
    }
