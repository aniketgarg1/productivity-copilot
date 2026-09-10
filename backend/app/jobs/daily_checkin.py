"""Background scheduler that triggers daily AI check-in calls."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import GoogleToken, UserProfile, TaskRecord, CallLog
from app.tools.twilio_caller import initiate_checkin_call
from app.tools.google_calendar import freebusy
from app.agents.checkin_agent import generate_checkin_greeting, generate_motivation

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

UTC = ZoneInfo("UTC")


def _utc_naive(dt: datetime) -> datetime:
    """
    Convert an aware datetime to naive UTC.

    created_at is a naive TIMESTAMP filled by the database's now(), so
    comparisons must happen in the same frame — passing a tz-aware local
    datetime made the "already called today" guard fire at the wrong times.
    """
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _is_user_busy(email: str, tz: ZoneInfo, db) -> bool:
    """Check Google Calendar to see if the user is currently in a meeting."""
    tok = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    if not tok:
        return False

    now = datetime.now(tz)
    window_end = now + timedelta(minutes=30)

    try:
        resp = freebusy(
            tok.token_json,
            now.astimezone(UTC).isoformat(),
            window_end.astimezone(UTC).isoformat(),
        )
        cal = resp.get("calendars", {}).get("primary", {})
        return bool(cal.get("busy"))
    except Exception:
        logger.warning("Could not check calendar for %s, proceeding with call", email)
        return False


def _checkin_for_profile(db, profile: UserProfile) -> None:
    tz = ZoneInfo(profile.timezone or settings.TIMEZONE)
    now_in_tz = datetime.now(tz)

    if now_in_tz.hour != profile.preferred_checkin_hour:
        return

    today_start = now_in_tz.replace(hour=0, minute=0, second=0, microsecond=0)
    already_called = (
        db.query(CallLog)
        .filter(
            CallLog.user_id == profile.id,
            CallLog.created_at >= _utc_naive(today_start),
        )
        .first()
    )
    if already_called:
        return

    if _is_user_busy(profile.email, tz, db):
        logger.info("Skipping check-in for %s — user is in a meeting", profile.email)
        return

    tasks = (
        db.query(TaskRecord)
        .filter(
            TaskRecord.user_id == profile.id,
            TaskRecord.status.in_(["pending", "in_progress", "done"]),
        )
        .order_by(TaskRecord.scheduled_start)
        .all()
    )

    task_list = [
        {"id": t.id, "title": t.title, "status": t.status, "estimate_minutes": t.estimate_minutes}
        for t in tasks
    ]
    pending = [t for t in task_list if t["status"] in ("pending", "in_progress")]

    coro = (
        generate_checkin_greeting(profile.name, task_list)
        if pending
        else generate_motivation(profile.name, task_list)
    )
    # asyncio.run creates, drives and disposes of the loop correctly; the old
    # hand-rolled new_event_loop() never called set_event_loop and leaked.
    ai_message = asyncio.run(coro)

    call_log = CallLog(user_id=profile.id, status="initiated", ai_message=ai_message)
    db.add(call_log)
    db.commit()
    db.refresh(call_log)

    sid = initiate_checkin_call(profile.phone, call_log.id, ai_message=ai_message)
    call_log.twilio_call_sid = sid
    db.commit()

    logger.info("Check-in call initiated for %s (sid: %s)", profile.email, sid)


def _run_daily_checkins():
    """
    Called at the top of every hour by APScheduler.
    For each user whose preferred_checkin_hour matches the current hour
    in their timezone, initiate a call — but only if they're not in a meeting.
    """
    if not settings.DAILY_CHECKIN_ENABLED:
        return
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_PHONE_NUMBER):
        logger.warning("Twilio not configured — skipping daily check-ins")
        return

    db = SessionLocal()
    try:
        profiles = db.query(UserProfile).filter(
            UserProfile.daily_checkin_enabled.is_(True),
            UserProfile.phone.isnot(None),
        ).all()

        for profile in profiles:
            try:
                _checkin_for_profile(db, profile)
            except Exception:
                logger.exception("Failed to initiate check-in call for %s", profile.email)
                db.rollback()
    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler — called once at app startup."""
    if not settings.DAILY_CHECKIN_ENABLED:
        logger.info("Daily check-in scheduler disabled")
        return

    # Cron at :00 rather than a 1-hour interval: an interval job is phased to
    # whenever the process started, so a restart could shift every check-in.
    scheduler.add_job(
        _run_daily_checkins,
        CronTrigger(minute=0),
        id="daily_checkin",
        replace_existing=True,
        misfire_grace_time=600,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("Daily check-in scheduler started (runs hourly on the hour)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
