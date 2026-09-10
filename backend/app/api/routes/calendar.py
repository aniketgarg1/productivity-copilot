from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_email, get_google_token
from app.db.session import get_db
from app.tools.google_calendar import create_test_event, ensure_fresh_token, freebusy

router = APIRouter(prefix="/calendar")


class FreeBusyRequest(BaseModel):
    timeMin: str
    timeMax: str


def _token_json(request: Request, db: Session) -> str:
    # Scope to the signed-in user — this used to return whichever token
    # happened to be first in the table.
    email = get_current_email(request)
    return ensure_fresh_token(db, get_google_token(db, email))


@router.get("/test-create-event")
def test_create_event(request: Request, db: Session = Depends(get_db)):
    return create_test_event(_token_json(request, db))


@router.post("/freebusy")
def freebusy_query(body: FreeBusyRequest, request: Request, db: Session = Depends(get_db)):
    return freebusy(_token_json(request, db), body.timeMin, body.timeMax)
