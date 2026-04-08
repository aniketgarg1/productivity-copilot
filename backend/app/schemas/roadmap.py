from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

Difficulty = Literal["easy", "medium", "hard"]
ResourceType = Literal["article", "video", "course", "docs", "tool", "exercise"]


class TaskResource(BaseModel):
    title: str
    url: str
    type: ResourceType


class RoadmapTask(BaseModel):
    title: str
    estimate_minutes: int = Field(..., ge=0)
    difficulty: Difficulty
    notes: Optional[str] = None
    resources: List[TaskResource] = Field(default_factory=list)


class RoadmapMilestone(BaseModel):
    title: str
    why_it_matters: str
    due_in_days: int = Field(..., ge=0)
    tasks: List[RoadmapTask]


class Roadmap(BaseModel):
    goal: str
    time_horizon_days: int = Field(..., ge=1)
    milestones: List[RoadmapMilestone]


class RoadmapOnlyResponse(BaseModel):
    roadmap: Roadmap


class CalendarEventOut(BaseModel):
    id: str
    htmlLink: str
    title: str
    start: str
    end: str


class ScheduleResponse(BaseModel):
    roadmap: Roadmap
    events: List[CalendarEventOut]
    message: Optional[str] = None