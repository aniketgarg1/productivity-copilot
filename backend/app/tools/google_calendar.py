import json
import logging
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.tools.google_oauth import SCOPES, creds_to_json

logger = logging.getLogger(__name__)


def creds_from_json(token_json: str) -> Credentials:
    data = json.loads(token_json)

    expiry = None
    raw_expiry = data.get("expiry")
    if raw_expiry:
        try:
            parsed = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
            # google-auth compares expiry against a naive UTC "now".
            expiry = parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            logger.warning("Ignoring unparseable Google token expiry: %r", raw_expiry)

    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or SCOPES,
        expiry=expiry,
    )


def _refresh_and_persist(token_json: str) -> tuple[Credentials, bool]:
    """
    Build credentials, refresh if expired, return (creds, was_refreshed).
    Caller is responsible for saving the updated token_json to the DB —
    see ``ensure_fresh_token``, which does that for you.
    """
    creds = creds_from_json(token_json)

    # An unknown expiry means the row predates expiry being stored; refresh once
    # so the persisted token gains one instead of silently 401-ing later.
    needs_refresh = creds.expired or not creds.token or creds.expiry is None

    if needs_refresh and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        logger.info("Google token refreshed automatically")
        return creds, True

    return creds, False


def updated_token_json(creds: Credentials) -> str:
    """Serialize refreshed credentials back to JSON for DB storage."""
    return creds_to_json(creds)


def ensure_fresh_token(db, token_row) -> str:
    """
    Refresh the stored Google credentials if needed and write the new token
    back to the DB, so the refresh actually sticks between requests.

    Returns the current (possibly updated) token JSON.
    """
    creds, refreshed = _refresh_and_persist(token_row.token_json)
    if refreshed:
        token_row.token_json = updated_token_json(creds)
        db.commit()
    return token_row.token_json


def build_calendar_service(token_json: str):
    """
    Build a Calendar API client.

    Reuse the returned service across calls in a request — constructing it
    performs credential work and (on first use) a discovery lookup.
    """
    creds, _ = _refresh_and_persist(token_json)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_test_event(token_json: str) -> dict:
    service = build_calendar_service(token_json)

    start = datetime.now(timezone.utc) + timedelta(minutes=10)
    end = start + timedelta(minutes=30)

    event = {
        "summary": "Productivity Copilot Test Task",
        "description": "Created by Productivity Copilot (testing)",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }

    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}


def freebusy(token_json: str, time_min_iso: str, time_max_iso: str) -> dict:
    service = build_calendar_service(token_json)
    body = {"timeMin": time_min_iso, "timeMax": time_max_iso, "items": [{"id": "primary"}]}
    return service.freebusy().query(body=body).execute()


def create_event(
    summary: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    timezone_name: str,
    task_id: str | None = None,
    token_json: str | None = None,
    service=None,
) -> dict:
    """
    Create a calendar event.

    Pass ``service`` to reuse one client across a batch of events; otherwise a
    client is built from ``token_json``.
    """
    if service is None:
        if not token_json:
            raise ValueError("create_event requires either a service or token_json")
        service = build_calendar_service(token_json)

    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone_name},
    }

    if task_id:
        event["extendedProperties"] = {
            "private": {"productivity_copilot_task_id": task_id}
        }

    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}


COPILOT_TASK_KEY = "productivity_copilot_task_id"


def event_task_id(event: dict) -> str | None:
    """The Copilot task id stamped on an event, if it is one of ours."""
    return ((event.get("extendedProperties") or {}).get("private") or {}).get(COPILOT_TASK_KEY)


def parse_event_times(event: dict) -> tuple[datetime | None, datetime | None]:
    """
    Read an event's start/end as datetimes.

    All-day events carry `date` instead of `dateTime`; treat those as unscheduled
    rather than guessing a time.
    """
    def _one(side: str) -> datetime | None:
        raw = (event.get(side) or {}).get("dateTime")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Unparseable %s on event %s: %r", side, event.get("id"), raw)
            return None

    return _one("start"), _one("end")


def update_event(
    event_id: str,
    start_dt: datetime,
    end_dt: datetime,
    timezone_name: str,
    token_json: str | None = None,
    service=None,
) -> dict:
    """Move an existing event. Only the times are touched."""
    if service is None:
        if not token_json:
            raise ValueError("update_event requires either a service or token_json")
        service = build_calendar_service(token_json)

    body = {
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone_name},
    }
    updated = service.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
    return {"id": updated.get("id"), "htmlLink": updated.get("htmlLink")}


def delete_event(event_id: str, token_json: str | None = None, service=None) -> bool:
    """
    Delete an event. Returns False when it was already gone, which is a
    success for our purposes, not an error.
    """
    from googleapiclient.errors import HttpError

    if service is None:
        if not token_json:
            raise ValueError("delete_event requires either a service or token_json")
        service = build_calendar_service(token_json)

    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except HttpError as exc:
        if exc.resp.status in (404, 410):
            return False
        raise


def list_events(
    time_min_iso: str,
    time_max_iso: str,
    token_json: str | None = None,
    service=None,
) -> list[dict]:
    if service is None:
        if not token_json:
            raise ValueError("list_events requires either a service or token_json")
        service = build_calendar_service(token_json)

    items: list[dict] = []
    page_token = None

    while True:
        resp = service.events().list(
            calendarId="primary",
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return items
