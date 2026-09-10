"""Twilio webhook routes for AI check-in phone calls."""

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.api.deps import get_current_email
from app.db.session import get_db
from app.db.models import GoogleToken, UserProfile, TaskRecord, CallLog
from app.agents.checkin_agent import generate_checkin_greeting, generate_followup, generate_motivation
from app.tools.google_calendar import freebusy
from app.tools.twilio_caller import escape_xml
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls")

TWIML_CONTENT_TYPE = "application/xml"


async def verify_twilio_signature(request: Request) -> None:
    """
    Reject webhook calls that aren't signed by Twilio.

    Without this, anyone who can guess a call_log_id can drive the call flow,
    burn LLM credits, and overwrite call logs.
    """
    if not settings.TWILIO_VALIDATE_SIGNATURE:
        return

    auth_token = settings.TWILIO_AUTH_TOKEN
    if not auth_token:
        raise HTTPException(status_code=503, detail="Twilio is not configured")

    from twilio.request_validator import RequestValidator

    signature = request.headers.get("X-Twilio-Signature", "")
    form = await request.form()
    params = {k: v for k, v in form.items() if isinstance(v, str)}

    # Twilio signs the URL it actually called, so honour proxy headers —
    # otherwise this never validates behind ngrok or a load balancer.
    url = str(request.url)
    proto = request.headers.get("X-Forwarded-Proto")
    if proto and proto != request.url.scheme:
        url = url.replace(f"{request.url.scheme}://", f"{proto}://", 1)

    if not RequestValidator(auth_token).validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


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


def _active_tasks(db: Session, user_id: int) -> list[TaskRecord]:
    return (
        db.query(TaskRecord)
        .filter(
            TaskRecord.user_id == user_id,
            TaskRecord.status.in_(["pending", "in_progress", "done"]),
        )
        .order_by(TaskRecord.scheduled_start)
        .all()
    )


def _twiml_say_gather(message: str, call_log_id: int, action: str = "respond") -> str:
    """Build TwiML that speaks a message and gathers speech input."""
    gather_url = f"{settings.BACKEND_URL.rstrip('/')}/calls/{action}/{call_log_id}"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{escape_xml(gather_url)}" method="POST"
            speechTimeout="3" timeout="10" language="en-US">
        <Say voice="Polly.Joanna">{escape_xml(message)}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn't hear anything. No worries, you can update your tasks in the app anytime. Have a great day!</Say>
</Response>"""


def _twiml_say(message: str) -> str:
    """Build TwiML that speaks a message and hangs up."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{escape_xml(message)}</Say>
</Response>"""


@router.post("/twiml/{call_log_id}", dependencies=[Depends(verify_twilio_signature)])
async def call_twiml(call_log_id: int, db: Session = Depends(get_db)):
    """
    Twilio fetches this when the call connects.
    Generates the AI greeting and asks the user for an update via speech.
    """
    call_log = db.query(CallLog).filter(CallLog.id == call_log_id).first()
    if not call_log:
        return Response(content=_twiml_say("Sorry, something went wrong. Goodbye."), media_type=TWIML_CONTENT_TYPE)

    user = db.query(UserProfile).filter(UserProfile.id == call_log.user_id).first()
    task_list = _task_dicts(_active_tasks(db, call_log.user_id))
    pending = [t for t in task_list if t["status"] in ("pending", "in_progress")]

    try:
        if pending:
            greeting = await generate_checkin_greeting(user.name if user else None, task_list)
        else:
            greeting = await generate_motivation(user.name if user else None, task_list)
    except Exception:
        # A live phone call is a bad place to return a 500.
        logger.exception("Failed to generate check-in greeting for call %s", call_log_id)
        greeting = "Hey! Just checking in on your tasks today. How's it going?"

    call_log.ai_message = greeting
    call_log.tasks_discussed = json.dumps([t["id"] for t in task_list])
    db.commit()

    return Response(content=_twiml_say_gather(greeting, call_log_id), media_type=TWIML_CONTENT_TYPE)


@router.post("/respond/{call_log_id}", dependencies=[Depends(verify_twilio_signature)])
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
    task_list = _task_dicts(_active_tasks(db, call_log.user_id))

    try:
        followup = await generate_followup(
            user_name=user.name if user else None,
            user_speech=SpeechResult,
            tasks=task_list,
            previous_ai_message=call_log.ai_message or "",
        )
    except Exception:
        logger.exception("Failed to generate follow-up for call %s", call_log_id)
        followup = "Thanks for the update!"

    closing = followup + " Have a productive day! Goodbye."
    return Response(content=_twiml_say(closing), media_type=TWIML_CONTENT_TYPE)


@router.post("/status/{call_log_id}", dependencies=[Depends(verify_twilio_signature)])
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


@router.post("/trigger")
async def trigger_checkin_call(request: Request, db: Session = Depends(get_db)):
    """
    Trigger a check-in call for the signed-in user (useful for testing).
    In production, the background scheduler triggers this automatically.

    This used to take the target email in the path with no authentication,
    which let anyone place a phone call to any registered user.
    """
    from app.tools.twilio_caller import initiate_checkin_call

    email = get_current_email(request)

    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    if not profile.phone:
        raise HTTPException(
            status_code=400,
            detail="No phone number registered. POST /tasks/register-phone first.",
        )
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_PHONE_NUMBER):
        raise HTTPException(status_code=503, detail="Twilio not configured")

    # Skip the call if the user is currently in a meeting.
    tok = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    if tok:
        try:
            tz = ZoneInfo(profile.timezone or settings.TIMEZONE)
            now = datetime.now(tz)
            resp = freebusy(
                tok.token_json,
                now.astimezone(ZoneInfo("UTC")).isoformat(),
                (now + timedelta(minutes=30)).astimezone(ZoneInfo("UTC")).isoformat(),
            )
            if (resp.get("calendars", {}).get("primary", {}) or {}).get("busy"):
                raise HTTPException(
                    status_code=409,
                    detail="You're currently in a meeting. The call will be skipped to avoid interrupting you.",
                )
        except HTTPException:
            raise
        except Exception:
            logger.warning("Calendar busy-check failed for %s; placing the call anyway", email)

    task_list = _task_dicts(_active_tasks(db, profile.id))
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
    except Exception as e:
        call_log.status = "failed"
        db.commit()
        logger.exception("Twilio call failed for %s", email)
        raise HTTPException(status_code=502, detail=f"Failed to initiate call: {e}")

    call_log.twilio_call_sid = sid
    db.commit()

    return {"message": "Check-in call initiated", "call_sid": sid, "call_log_id": call_log.id}


@router.get("/history")
async def call_history(request: Request, db: Session = Depends(get_db)):
    """Return the most recent check-in calls for the authenticated user."""
    email = get_current_email(request)

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
