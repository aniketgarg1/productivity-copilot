"""Analytics endpoint — task completion stats and streaks."""

from datetime import date, datetime, timedelta, timezone
from collections import Counter
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.db.models import UserProfile, TaskRecord
from app.api.deps import get_current_email

router = APIRouter(prefix="/analytics")


@router.get("")
async def analytics(request: Request, db: Session = Depends(get_db)):
    """Return task analytics for the authenticated user."""
    email = get_current_email(request)

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

    # updated_at is stored as naive UTC, but "today" means today for the user.
    tz = ZoneInfo(profile.timezone or settings.TIMEZONE)

    def _local_date(dt) -> date:
        return dt.replace(tzinfo=timezone.utc).astimezone(tz).date()

    # Streak: consecutive days (backwards from today) with at least one "done" task
    done_dates: set[date] = {
        _local_date(t.updated_at) for t in tasks if t.status == "done" and t.updated_at
    }

    today = datetime.now(tz).date()

    streak = 0
    check = today
    # A streak shouldn't reset just because today isn't over yet.
    if check not in done_dates:
        check -= timedelta(days=1)
    while check in done_dates:
        streak += 1
        check -= timedelta(days=1)

    # Daily completions for the last 30 days
    thirty_days_ago = today - timedelta(days=29)
    recent_done = Counter(
        d
        for d in (_local_date(t.updated_at) for t in tasks if t.status == "done" and t.updated_at)
        if d >= thirty_days_ago
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
