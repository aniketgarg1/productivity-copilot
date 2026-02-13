import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from itsdangerous import URLSafeSerializer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import GoogleToken
from app.db.session import get_db
from app.tools.google_oauth import build_flow, fetch_user_email, creds_to_json

router = APIRouter(prefix="/auth/google")


def _serializer():
    return URLSafeSerializer(settings.SESSION_SECRET, salt="google-oauth-state")


@router.get("/start")
async def start_google_oauth(response: Response):
    flow = build_flow()

    state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )

    signed = _serializer().dumps({"state": state})
    response.set_cookie("oauth_state", signed, httponly=True, samesite="lax")
    return {"auth_url": auth_url}


@router.get("/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    cookie = request.cookies.get("oauth_state")
    if not cookie:
        raise HTTPException(status_code=400, detail="Missing oauth_state cookie")

    try:
        data = _serializer().loads(cookie)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid oauth_state cookie")

    if data.get("state") != state:
        raise HTTPException(status_code=400, detail="State mismatch")

    flow = build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    email = await fetch_user_email(creds.token)
    token_json = creds_to_json(creds)

    existing = db.query(GoogleToken).filter(GoogleToken.email == email).first()
    if existing:
        existing.token_json = token_json
    else:
        db.add(GoogleToken(email=email, token_json=token_json))
    db.commit()

    resp = Response(content="Google account connected. You can close this tab.")
    resp.delete_cookie("oauth_state")
    return resp


@router.get("/status")
def status(db: Session = Depends(get_db)):
    tok = db.query(GoogleToken).first()
    return {"connected": bool(tok), "email": tok.email if tok else None}
