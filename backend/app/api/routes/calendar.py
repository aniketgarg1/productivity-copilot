from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import GoogleToken
from app.db.session import get_db
from app.tools.google_calendar import create_test_event, freebusy

router = APIRouter(prefix="/calendar")


def _get_token(db: Session) -> GoogleToken:
    tok = db.query(GoogleToken).first()
    if not tok:
        raise HTTPException(status_code=400, detail="No Google account connected. Use /auth/google/start")
    return tok


@router.get("/test-create-event")
def test_create_event(db: Session = Depends(get_db)):
    tok = _get_token(db)
    return create_test_event(tok.token_json)


@router.post("/freebusy")
def freebusy_query(payload: dict, db: Session = Depends(get_db)):
    tok = _get_token(db)
    time_min = payload.get("timeMin")
    time_max = payload.get("timeMax")
    if not time_min or not time_max:
        raise HTTPException(status_code=400, detail="timeMin/timeMax required")
    return freebusy(tok.token_json, time_min, time_max)
