"""Twilio outbound call utility for daily check-in calls."""

from xml.sax.saxutils import escape

from app.core.config import settings

# Twilio only accepts these four values for StatusCallbackEvent; sending
# "failed"/"busy"/"no-answer" makes the whole call request 400.
STATUS_CALLBACK_EVENTS = ["initiated", "ringing", "answered", "completed"]

DEFAULT_MESSAGE = (
    "Hey! This is your productivity copilot. Keep up the great work on your tasks today!"
)


def _get_client():
    from twilio.rest import Client

    sid = settings.TWILIO_ACCOUNT_SID
    token = settings.TWILIO_AUTH_TOKEN
    if not sid or not token:
        raise RuntimeError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not configured")
    return Client(sid, token)


def escape_xml(text: str) -> str:
    """Escape text for inclusion in TwiML (&, <, >, plus both quote styles)."""
    return escape(text or "", {'"': "&quot;", "'": "&apos;"})


def initiate_checkin_call(to_phone: str, call_log_id: int, ai_message: str = "") -> str:
    """
    Start an outbound check-in call.

    If BACKEND_URL is publicly reachable, Twilio fetches TwiML from the webhook
    so the call is interactive. Otherwise inline TwiML is sent (speak-only, no
    gather) so local development works without ngrok.
    """
    if not settings.TWILIO_PHONE_NUMBER:
        raise RuntimeError("TWILIO_PHONE_NUMBER not configured")

    client = _get_client()
    backend = settings.BACKEND_URL.rstrip("/")

    if settings.backend_is_public:
        call = client.calls.create(
            to=to_phone,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=f"{backend}/calls/twiml/{call_log_id}",
            status_callback=f"{backend}/calls/status/{call_log_id}",
            status_callback_event=STATUS_CALLBACK_EVENTS,
            status_callback_method="POST",
            method="POST",
        )
    else:
        # Local dev: send inline TwiML so the call works without a public URL.
        escaped = escape_xml(ai_message or DEFAULT_MESSAGE)
        twiml = (
            f"<Response>"
            f'<Say voice="Polly.Joanna">{escaped}</Say>'
            f'<Pause length="1"/>'
            f'<Say voice="Polly.Joanna">Remember, you can update your task progress '
            f"in the app anytime. Have a productive day!</Say>"
            f"</Response>"
        )
        call = client.calls.create(
            to=to_phone,
            from_=settings.TWILIO_PHONE_NUMBER,
            twiml=twiml,
        )

    return call.sid
