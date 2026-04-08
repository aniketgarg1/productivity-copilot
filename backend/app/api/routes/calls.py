"""Twilio webhook routes for AI check-in phone calls."""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.db.session import get_db
from app.db.models import GoogleToken, UserProfile, TaskRecord, CallLog
from app.agents.checkin_agent import generate_checkin_greeting, generate_followup, generate_motivation
from app.api.routes.schedule import _get_current_email
from app.tools.google_calendar import freebusy
from app.core.config import settings

router = APIRouter(prefix="/calls")

TWIML_CONTENT_TYPE = "application/xml"


def _task_dicts(tasks: list[TaskRecord]) -> list[dict]:
    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "estimate_minutes": t.estimate_minutes,
        }
        for t in tasks
    ]


def _twiml_say_gather(message: str, call_log_id: int, action: str = "respond") -> str:
    """Build TwiML that speaks a message and gathers speech input."""
    gather_url = f"{settings.BACKEND_URL}/calls/{action}/{call_log_id}"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{gather_url}" method="POST"
            speechTimeout="3" timeout="10" language="en-US">
        <Say voice="Polly.Joanna">{_escape_xml(message)}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn't hear anything. No worries, you can update your tasks in the app anytime. Have a great day!</Say>
</Response>"""


def _twiml_say(message: str) -> str:
    """Build TwiML that speaks a message and hangs up."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{_escape_xml(message)}</Say>
</Response>"""


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@router.post("/twiml/{call_log_id}")
async def call_twiml(call_log_id: int, db: Session = Depends(get_db)):
    """
    Twilio fetches this when the call connects.
    Generates the AI greeting and asks the user for an update via speech.
    """
    call_log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if not call_log:
        return Response(content=_twiml_say("Sorry, something went wrong. Goodbye."), media_type=TWIML_CONTENT_TYPE)

    user = db.query(UserProfile).filter(UserProfile.id == call_log.user_id).first()
    tasks = db.query(TaskRecord).filter(
        TaskRecord.user_id == call_log.user_id,
        TaskRecord.status.in_(["pending", "in_progress", "done"]),
    ).order_by(TaskRecord.scheduled_start).all()

    task_list = _task_dicts(tasks)
    pending = [t for t in task_list if t["status"] in ("pending", "in_progress")]

    if pending:
        greeting = await generate_checkin_greeting(user.name if user else None, task_list)
    else:
        greeting = await generate_motivation(user.name if user else None, task_list)

    call_log.ai_message = greeting
    call_log.tasks_discussed = json.dumps([t["id"] for t in task_list])
    db.commit()

    twiml = _twiml_say_gather(greeting, call_log_id)
    return Response(content=twiml, media_type=TWIML_CONTENT_TYPE)


@router.post("/respond/{call_log_id}")
async def call_respond(
    call_log_id: int,
    SpeechResult: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """
    Twilio sends the user's speech transcription here.
    AI processes it and replies with encouragement.
    """
    call_log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if not call_log:
        return Response(content=_twiml_say("Goodbye!"), media_type=TWIML_CONTENT_TYPE)

    call_log.user_response = SpeechResult
    db.commit()

    user = db.query(UserProfile).filter(UserProfile.id == call_log.user_id).first()
    tasks = db.query(TaskRecord).filter(
        TaskRecord.user_id == call_log.user_id,
        TaskRecord.status.in_(["pending", "in_progress", "done"]),
    ).order_by(TaskRecord.scheduled_start).all()

    task_list = _task_dicts(tasks)

    followup = await generate_followup(
        user_name=user.name if user else None,
        user_speech=SpeechResult,
        tasks=task_list,
        previous_ai_message=call_log.ai_message or "",
    )

    closing = followup + " Have a productive day! Goodbye."
    twiml = _twiml_say(closing)
    return Response(content=twiml, media_type=TWIML_CONTENT_TYPE)


@router.post("/status/{call_log_id}")
async def call_status(
    call_log_id: int,
    CallStatus: str = Form(default=""),
    CallSid: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Twilio status callback — update the call log when the call ends."""
    call_log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if call_log:
        call_log.status = CallStatus
        if CallSid:
            call_log.twilio_call_sid = CallSid
        db.commit()
    return {"ok": True}


@router.post("/trigger/{email}")
async def trigger_checkin_call(email: str, db: Session = Depends(get_db)):
    """
    Manually trigger a check-in call for a user (useful for testing).
    In production, the background scheduler triggers this automatically.
    """
    from app.tools.twilio_caller import initiate_checkin_call

    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    if not profile.phone:
        raise HTTPException(status_code=400, detail="No phone number registered")
    if not settings.TWILIO_ACCOUNT_SID:
        raise HTTPException(status_code=500, detail="Twilio not configured")

    # Check if user is currently in a meeting
    tok = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    if tok:
        try:
            tz = ZoneInfo(profile.timezone or settings.TIMEZONE)
            now = datetime.now(tz)
            window_end = now + timedelta(minutes=30)
            resp = freebusy(
                tok.token_json,
                now.astimezone(ZoneInfo("UTC")).isoformat(),
                window_end.astimezone(ZoneInfo("UTC")).isoformat(),
            )
            cal = resp.get("calendars", {}).get("primary", {})
            if cal.get("busy"):
                raise HTTPException(
                    status_code=409,
                    detail="You're currently in a meeting. The call will be skipped to avoid interrupting you."
                )
        except HTTPException:
            raise
        except Exception:
            pass  # if calendar check fails, proceed with call

    # Fetch tasks and pre-generate AI message for inline TwiML (local dev)
    tasks = db.query(TaskRecord).filter(
        TaskRecord.user_id == profile.id,
        TaskRecord.status.in_(["pending", "in_progress", "done"]),
    ).order_by(TaskRecord.scheduled_start).all()

    task_list = _task_dicts(tasks)
    pending = [t for t in task_list if t["status"] in ("pending", "in_progress")]

    if pending:
        ai_message = await generate_checkin_greeting(profile.name, task_list)
    else:
        ai_message = await generate_motivation(profile.name, task_list)

    call_log = CallLog(user_id=profile.id, status="initiated", ai_message=ai_message)
    db.add(call_log)
    db.commit()
    db.refresh(call_log)

    try:
        sid = initiate_checkin_call(profile.phone, call_log.id, ai_message=ai_message)
        call_log.twilio_call_sid = sid
        db.commit()
    except Exception as e:
        call_log.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {e}")

    return {"message": "Check-in call initiated", "call_sid": sid, "call_log_id": call_log.id}


@router.get("/history")
async def call_history(request: Request, db: Session = Depends(get_db)):
    """Return the most recent check-in calls for the authenticated user."""
    email = _get_current_email(request)

    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        return {"calls": []}

    logs = (
        db.query(CallLog)
        .filter(CallLog.user_id == profile.id)
        .order_by(CallLog.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "calls": [
            {
                "id": log.id,
                "status": log.status,
                "ai_message": log.ai_message,
                "user_response": log.user_response,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }
