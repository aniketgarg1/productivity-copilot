"""Background scheduler that triggers daily AI check-in calls."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import GoogleToken, UserProfile, TaskRecord, CallLog
from app.tools.twilio_caller import initiate_checkin_call
from app.tools.google_calendar import freebusy
from app.agents.checkin_agent import generate_checkin_greeting, generate_motivation

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


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
            now.astimezone(ZoneInfo("UTC")).isoformat(),
            window_end.astimezone(ZoneInfo("UTC")).isoformat(),
        )
        cal = resp.get("calendars", {}).get("primary", {})
        busy_slots = cal.get("busy", [])
        return len(busy_slots) > 0
    except Exception:
        logger.warning("Could not check calendar for %s, proceeding with call", email)
        return False


def _run_daily_checkins():
    """
    Called once per hour by APScheduler.
    For each user whose preferred_checkin_hour matches the current hour
    in their timezone, initiate a call — but only if they're not in a meeting.
    """
    if not settings.DAILY_CHECKIN_ENABLED:
        return
    if not settings.TWILIO_ACCOUNT_SID:
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
                tz = ZoneInfo(profile.timezone or settings.TIMEZONE)
                now_in_tz = datetime.now(tz)

                if now_in_tz.hour != profile.preferred_checkin_hour:
                    continue

                today_start = now_in_tz.replace(hour=0, minute=0, second=0, microsecond=0)
                already_called = db.query(CallLog).filter(
                    CallLog.user_id == profile.id,
                    CallLog.created_at >= today_start,
                ).first()
                if already_called:
                    continue

                if _is_user_busy(profile.email, tz, db):
                    logger.info("Skipping check-in for %s — user is in a meeting", profile.email)
                    continue

                tasks = db.query(TaskRecord).filter(
                    TaskRecord.user_id == profile.id,
                    TaskRecord.status.in_(["pending", "in_progress", "done"]),
                ).order_by(TaskRecord.scheduled_start).all()

                task_list = [
                    {"id": t.id, "title": t.title, "status": t.status, "estimate_minutes": t.estimate_minutes}
                    for t in tasks
                ]
                pending = [t for t in task_list if t["status"] in ("pending", "in_progress")]

                loop = asyncio.new_event_loop()
                try:
                    if pending:
                        ai_message = loop.run_until_complete(
                            generate_checkin_greeting(profile.name, task_list)
                        )
                    else:
                        ai_message = loop.run_until_complete(
                            generate_motivation(profile.name, task_list)
                        )
                finally:
                    loop.close()

                call_log = CallLog(user_id=profile.id, status="initiated", ai_message=ai_message)
                db.add(call_log)
                db.commit()
                db.refresh(call_log)

                sid = initiate_checkin_call(profile.phone, call_log.id, ai_message=ai_message)
                call_log.twilio_call_sid = sid
                db.commit()

                logger.info("Check-in call initiated for %s (sid: %s)", profile.email, sid)

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

    scheduler.add_job(
        _run_daily_checkins,
        "interval",
        hours=1,
        id="daily_checkin",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Daily check-in scheduler started (runs every hour)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
