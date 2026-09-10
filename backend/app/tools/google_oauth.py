import json

import httpx
from google_auth_oauthlib.flow import Flow

from app.core.config import settings

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar",  # read/write
]


def _client_config():
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in env")

    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def build_flow() -> Flow:
    return Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )


async def fetch_user_email(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        email = r.json().get("email")

    if not email:
        raise RuntimeError("Google did not return an email for this account")
    return email


def creds_to_json(creds) -> str:
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
        # Without expiry, Credentials.expired is always False and the access
        # token is never refreshed — every Calendar call 401s after ~1 hour.
        "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
    }
    return json.dumps(payload)
