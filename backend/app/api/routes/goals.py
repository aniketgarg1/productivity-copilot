from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.llm.factory import get_llm
from app.agents.planner import make_roadmap, run_intake_conversation

router = APIRouter(prefix="/goals")


class GoalTextRequest(BaseModel):
    goal: str = Field(..., min_length=3, max_length=1000)
    horizon_days: int = Field(30, ge=1, le=365)


@router.post("/text")
async def goals_text(req: GoalTextRequest):
    llm = get_llm()
    roadmap = await make_roadmap(llm, req.goal, req.horizon_days)
    return {"roadmap": roadmap}


class IntakeMessage(BaseModel):
    role: str
    content: str


class IntakeChatRequest(BaseModel):
    messages: list[IntakeMessage]


@router.post("/intake")
async def goal_intake(req: IntakeChatRequest):
    """
    Conversational goal intake. The AI asks questions to deeply understand
    the user's goal, experience level, and blockers before creating a roadmap.
    Returns {"type": "question", "message": "..."} or {"type": "ready", "summary": "..."}
    """
    llm = get_llm()
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    result = await run_intake_conversation(llm, messages)
    return result