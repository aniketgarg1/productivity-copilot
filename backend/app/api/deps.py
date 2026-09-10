"""Shared request dependencies (session cookie auth, token lookup)."""

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import GoogleToken

USER_COOKIE = "pc_user"
OAUTH_STATE_COOKIE = "oauth_state"

_RECONNECT = "Reconnect Google at /auth/google/start"


def user_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.SESSION_SECRET, salt="pc-user-session")


def oauth_state_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.SESSION_SECRET, salt="google-oauth-state")


def cookie_kwargs() -> dict:
    """Cookie flags: Secure is required once the app is served over HTTPS."""
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": not settings.DEV_MODE,
    }


def get_current_email(request: Request) -> str:
    """Read the signed session cookie and return the authenticated email."""
    cookie = request.cookies.get(USER_COOKIE)
    if not cookie:
        raise HTTPException(status_code=401, detail=f"Not authenticated. {_RECONNECT}")

    try:
        data = user_serializer().loads(cookie)
    except BadSignature:
        raise HTTPException(status_code=401, detail=f"Invalid session. {_RECONNECT}")
    except Exception:
        raise HTTPException(status_code=401, detail=f"Invalid session. {_RECONNECT}")

    email = data.get("email") if isinstance(data, dict) else None
    if not email:
        raise HTTPException(status_code=401, detail=f"Missing user session. {_RECONNECT}")

    return email


def get_google_token(db: Session, email: str) -> GoogleToken:
    tok = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    if not tok:
        raise HTTPException(
            status_code=401,
            detail="No Google account connected for this user. Use /auth/google/start",
        )
    return tok
