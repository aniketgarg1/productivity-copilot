import json
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from zoneinfo import ZoneInfo
from app.tools.google_oauth import SCOPES

def creds_from_json(token_json: str) -> Credentials:
    data = json.loads(token_json)

    # Always enforce the app's required scopes (not whatever was stored earlier)
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=SCOPES,
    )


def build_calendar_service(token_json: str):
    creds = creds_from_json(token_json)
    return build("calendar", "v3", credentials=creds)


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

def create_event(token_json: str, summary: str, description: str, start_dt: datetime, end_dt: datetime, timezone: str) -> dict:
    service = build_calendar_service(token_json)

    tz = ZoneInfo(timezone)
    # ensure timezone-aware
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=tz)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=tz)

    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
    }

    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}