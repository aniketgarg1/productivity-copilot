from __future__ import annotations
from typing import Any, Dict

ROADMAP_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string"},
        "time_horizon_days": {"type": "integer", "minimum": 1, "maximum": 3650},
        "milestones": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "due_in_days": {"type": "integer", "minimum": 1, "maximum": 3650},
                    "tasks": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "estimate_minutes": {"type": "integer", "minimum": 10, "maximum": 480},
                                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                                "notes": {"type": "string"},
                            },
                            "required": ["title", "estimate_minutes", "difficulty", "notes"],
                        },
                    },
                },
                "required": ["title", "why_it_matters", "due_in_days", "tasks"],
            },
        },
    },
    "required": ["goal", "time_horizon_days", "milestones"],
}


async def make_roadmap(llm, goal_text: str, horizon_days: int = 30) -> Dict[str, Any]:
    system = (
        "You are a planning agent. Create an actionable roadmap with milestones and tasks. "
        "Be realistic for a busy student. Keep tasks small and schedulable."
    )
    user = f"""
Goal: {goal_text}
Time horizon (days): {horizon_days}

Return ONLY valid JSON that matches the provided schema.
"""
    return await llm.generate_json(
        system=system,
        user=user,
        schema_name="goal_roadmap",
        schema=ROADMAP_SCHEMA,
        strict=True,
        temperature=0.2,
    )