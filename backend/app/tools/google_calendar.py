import json
import logging
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from zoneinfo import ZoneInfo
from app.tools.google_oauth import SCOPES

logger = logging.getLogger(__name__)


def creds_from_json(token_json: str) -> Credentials:
    data = json.loads(token_json)

    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=SCOPES,
    )


def _refresh_and_persist(token_json: str) -> tuple[Credentials, bool]:
    """
    Build credentials, refresh if expired, return (creds, was_refreshed).
    Caller is responsible for saving the updated token_json to the DB.
    """
    creds = creds_from_json(token_json)

    if creds.expired or not creds.token:
        if creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            logger.info("Google token refreshed automatically")
            return creds, True
    return creds, False


def updated_token_json(creds: Credentials) -> str:
    """Serialize refreshed credentials back to JSON for DB storage."""
    from app.tools.google_oauth import creds_to_json
    return creds_to_json(creds)


def build_calendar_service(token_json: str):
    creds, _ = _refresh_and_persist(token_json)
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

def create_event(
    token_json: str,
    summary: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    timezone: str,
    task_id: str | None = None,
) -> dict:
    service = build_calendar_service(token_json)
    ...
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
    }

    if task_id:
        event["extendedProperties"] = {
            "private": {"productivity_copilot_task_id": task_id}
        }

    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}
    
def list_events(token_json: str, time_min_iso: str, time_max_iso: str) -> list[dict]:
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