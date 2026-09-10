import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    OAUTH_STATE_COOKIE,
    USER_COOKIE,
    cookie_kwargs,
    oauth_state_serializer,
    user_serializer,
)
from app.core.config import settings
from app.db.models import GoogleToken
from app.db.session import get_db
from app.tools.google_oauth import build_flow, fetch_user_email, creds_to_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google")


# Google's consent screen can take a while to click through (account picker,
# plus the "unverified app" interstitial while the project is in Testing).
OAUTH_STATE_TTL_SECONDS = 30 * 60


def _build_auth_url() -> tuple[str, str]:
    """Return (auth_url, signed_state_cookie)."""
    flow = build_flow()

    state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url, oauth_state_serializer().dumps({"state": state})


@router.get("/login")
async def login_google_oauth():
    """
    Browser entry point: sets the state cookie and redirects straight to Google.

    Prefer this over /start when clicking through by hand — the cookie and the
    redirect happen in one navigation, so the cookie can't end up in a
    different browser than the one that finishes the consent flow.
    """
    auth_url, signed = _build_auth_url()
    resp = RedirectResponse(url=auth_url, status_code=302)
    resp.set_cookie(OAUTH_STATE_COOKIE, signed, max_age=OAUTH_STATE_TTL_SECONDS, **cookie_kwargs())
    return resp


@router.get("/start")
async def start_google_oauth(response: Response):
    """
    JSON variant for a frontend that wants the URL itself.

    The caller must send the response's cookie back on the callback, so the
    fetch needs `credentials: "include"` and the user must open the returned
    URL in that same browser.
    """
    auth_url, signed = _build_auth_url()
    response.set_cookie(OAUTH_STATE_COOKIE, signed, max_age=OAUTH_STATE_TTL_SECONDS, **cookie_kwargs())
    return {"auth_url": auth_url}


@router.get("/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(status_code=400, detail=f"Google returned an error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    cookie = request.cookies.get(OAUTH_STATE_COOKIE)
    if not cookie:
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing oauth_state cookie. This happens when the consent screen was "
                "opened in a different browser than the one that started the flow, or "
                "when it took over 30 minutes. Open "
                f"{settings.BACKEND_URL.rstrip('/')}/auth/google/login directly in your "
                "browser to do the whole flow in one go."
            ),
        )

    try:
        data = oauth_state_serializer().loads(cookie)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid oauth_state cookie")

    if not secrets.compare_digest(str(data.get("state", "")), state):
        raise HTTPException(status_code=400, detail="State mismatch")

    flow = build_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        logger.exception("Google token exchange failed")
        raise HTTPException(status_code=400, detail=f"Google token exchange failed: {exc}")

    creds = flow.credentials
    email = await fetch_user_email(creds.token)
    token_json = creds_to_json(creds)

    # Upsert by email. (This used to wipe the whole table, which logged out
    # every other connected account whenever anyone signed in.)
    existing = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    if existing:
        # Google omits refresh_token on re-consent in some flows — keep the old one.
        if not creds.refresh_token:
            import json

            merged = json.loads(token_json)
            merged["refresh_token"] = json.loads(existing.token_json).get("refresh_token")
            token_json = json.dumps(merged)
        existing.token_json = token_json
    else:
        db.add(GoogleToken(email=email, token_json=token_json))
    db.commit()

    resp = RedirectResponse(url=f"{settings.FRONTEND_URL.rstrip('/')}/dashboard", status_code=302)
    resp.delete_cookie(OAUTH_STATE_COOKIE)
    resp.set_cookie(
        USER_COOKIE,
        user_serializer().dumps({"email": email}),
        max_age=60 * 60 * 24 * 30,
        **cookie_kwargs(),
    )
    return resp


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)):
    cookie = request.cookies.get(USER_COOKIE)
    if not cookie:
        return {"connected": False, "email": None}

    try:
        data = user_serializer().loads(cookie)
        email = data.get("email")
    except Exception:
        return {"connected": False, "email": None}

    tok = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    return {"connected": bool(tok), "email": email if tok else None}


@router.post("/logout")
def logout():
    resp = RedirectResponse(url=settings.FRONTEND_URL, status_code=302)
    resp.delete_cookie(USER_COOKIE)
    return resp
