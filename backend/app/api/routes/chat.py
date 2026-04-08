"""Chat endpoint — conversational assistant with task context."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import UserProfile, TaskRecord
from app.api.routes.schedule import _get_current_email
from app.llm.factory import get_llm

router = APIRouter(prefix="/chat")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("")
async def chat(body: ChatRequest, request: Request, db: Session = Depends(get_db)):
    """Send a message to the AI assistant with the user's tasks as context."""
    email = _get_current_email(request)

    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    tasks_context = ""
    if profile:
        tasks = (
            db.query(TaskRecord)
            .filter(TaskRecord.user_id == profile.id)
            .order_by(TaskRecord.scheduled_start)
            .all()
        )
        if tasks:
            lines = []
            for t in tasks:
                start = t.scheduled_start.strftime("%b %d %H:%M") if t.scheduled_start else "unscheduled"
                lines.append(f"- [{t.status}] {t.title} ({t.estimate_minutes}min, {start})")
            tasks_context = "\n".join(lines)

    system_prompt = (
        "You are a helpful productivity assistant. "
        "You help the user stay on track with their goals and tasks. "
        "Be concise, encouraging, and actionable.\n"
    )
    if tasks_context:
        system_prompt += f"\nThe user's current tasks:\n{tasks_context}\n"

    conversation = "\n".join(
        f"{m.role}: {m.content}" for m in body.history
    )
    user_input = f"{conversation}\nuser: {body.message}" if conversation else body.message

    llm = get_llm()
    reply = await llm.generate_text(system=system_prompt, user=user_input, temperature=0.7)

    return {"reply": reply}
