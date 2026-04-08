"""Analytics endpoint — task completion stats and streaks."""

from datetime import date, timedelta
from collections import Counter

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import UserProfile, TaskRecord
from app.api.routes.schedule import _get_current_email

router = APIRouter(prefix="/analytics")


@router.get("")
async def analytics(request: Request, db: Session = Depends(get_db)):
    """Return task analytics for the authenticated user."""
    email = _get_current_email(request)

    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        return {
            "total_tasks": 0,
            "completed": 0,
            "in_progress": 0,
            "pending": 0,
            "skipped": 0,
            "completion_rate": 0.0,
            "total_scheduled_minutes": 0,
            "total_completed_minutes": 0,
            "streak_days": 0,
            "daily_completions": [],
        }

    tasks = db.query(TaskRecord).filter(TaskRecord.user_id == profile.id).all()

    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == "done")
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    pending = sum(1 for t in tasks if t.status == "pending")
    skipped = sum(1 for t in tasks if t.status == "skipped")

    completion_rate = round((completed / total) * 100, 1) if total else 0.0

    total_scheduled_minutes = sum(t.estimate_minutes for t in tasks if t.estimate_minutes)
    total_completed_minutes = sum(
        t.estimate_minutes for t in tasks if t.status == "done" and t.estimate_minutes
    )

    # Streak: consecutive days (backwards from today) with at least one "done" task
    done_dates: set[date] = set()
    for t in tasks:
        if t.status == "done" and t.updated_at:
            done_dates.add(t.updated_at.date())

    streak = 0
    check = date.today()
    while check in done_dates:
        streak += 1
        check -= timedelta(days=1)

    # Daily completions for the last 30 days
    today = date.today()
    thirty_days_ago = today - timedelta(days=29)
    recent_done = Counter(
        t.updated_at.date()
        for t in tasks
        if t.status == "done" and t.updated_at and t.updated_at.date() >= thirty_days_ago
    )
    daily_completions = [
        {"date": (thirty_days_ago + timedelta(days=i)).isoformat(),
         "count": recent_done.get(thirty_days_ago + timedelta(days=i), 0)}
        for i in range(30)
    ]

    return {
        "total_tasks": total,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "skipped": skipped,
        "completion_rate": completion_rate,
        "total_scheduled_minutes": total_scheduled_minutes,
        "total_completed_minutes": total_completed_minutes,
        "streak_days": streak,
        "daily_completions": daily_completions,
    }
