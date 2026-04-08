"""Twilio outbound call utility for daily check-in calls."""

from app.core.config import settings


def _get_client():
    from twilio.rest import Client

    sid = settings.TWILIO_ACCOUNT_SID
    token = settings.TWILIO_AUTH_TOKEN
    if not sid or not token:
        raise RuntimeError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not configured")
    return Client(sid, token)


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def initiate_checkin_call(to_phone: str, call_log_id: int, ai_message: str = "") -> str:
    """
    Start an outbound call with inline TwiML (no public webhook URL needed).
    If BACKEND_URL is publicly reachable, uses webhook for interactive calls.
    Otherwise, falls back to inline TwiML (speak-only, no gather).
    """
    client = _get_client()
    backend = settings.BACKEND_URL

    is_public = backend and not any(
        h in backend for h in ("localhost", "127.0.0.1", "0.0.0.0")
    )

    if is_public:
        call = client.calls.create(
            to=to_phone,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=f"{backend}/calls/twiml/{call_log_id}",
            status_callback=f"{backend}/calls/status/{call_log_id}",
            status_callback_event=["completed", "failed", "busy", "no-answer"],
            method="POST",
        )
    else:
        # Local dev: send inline TwiML so the call works without ngrok
        escaped = _escape_xml(ai_message) if ai_message else "Hey! This is your productivity copilot. Keep up the great work on your tasks today!"
        twiml = (
            f'<Response>'
            f'<Say voice="Polly.Joanna">{escaped}</Say>'
            f'<Pause length="1"/>'
            f'<Say voice="Polly.Joanna">Remember, you can update your task progress in the app anytime. Have a productive day!</Say>'
            f'</Response>'
        )
        call = client.calls.create(
            to=to_phone,
            from_=settings.TWILIO_PHONE_NUMBER,
            twiml=twiml,
        )

    return call.sid
