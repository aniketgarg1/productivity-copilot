from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.llm.factory import get_llm
from app.agents.planner import make_roadmap

router = APIRouter(prefix="/goals")


class GoalTextRequest(BaseModel):
    goal: str = Field(..., min_length=3, max_length=1000)
    horizon_days: int = Field(30, ge=1, le=365)


@router.post("/text")
async def goals_text(req: GoalTextRequest):
    llm = get_llm()
    roadmap = await make_roadmap(llm, req.goal, req.horizon_days)
    return {"roadmap": roadmap}