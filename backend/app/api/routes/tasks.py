"""Task progress tracking — view, update status, and manage tasks."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Literal

from app.db.session import get_db
from app.db.models import UserProfile, TaskRecord
from app.api.routes.schedule import _get_current_email

router = APIRouter(prefix="/tasks")


class TaskStatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "done", "skipped"]
    progress_note: str | None = None


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
    email = _get_current_email(request)
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
            }
            for t in tasks
        ]
    }


@router.patch("/{task_id}")
async def update_task_status(
    task_id: int,
    body: TaskStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update the status of a task (pending, in_progress, done, skipped)."""
    email = _get_current_email(request)
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
    email = _get_current_email(request)

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
