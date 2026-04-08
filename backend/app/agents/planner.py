from __future__ import annotations
from typing import Any, Dict, List

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
                                "resources": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "title": {"type": "string"},
                                            "url": {"type": "string"},
                                            "type": {"type": "string", "enum": ["article", "video", "course", "docs", "tool", "exercise"]},
                                        },
                                        "required": ["title", "url", "type"],
                                    },
                                },
                            },
                            "required": ["title", "estimate_minutes", "difficulty", "notes", "resources"],
                        },
                    },
                },
                "required": ["title", "why_it_matters", "due_in_days", "tasks"],
            },
        },
    },
    "required": ["goal", "time_horizon_days", "milestones"],
}


async def make_roadmap(llm, goal_text: str, horizon_days: int = 30, context: str = "") -> Dict[str, Any]:
    system = (
        "You are an expert planning and learning coach. Create a highly actionable roadmap with milestones and tasks. "
        "Be realistic for a busy person. Keep tasks small and schedulable (10-120 min each).\n\n"
        "CRITICAL RULE FOR RESOURCES: For every task, include 1-3 resource links. "
        "You MUST ONLY use URLs from the VERIFIED LIST below. Do NOT invent or guess URLs. "
        "Do NOT use deep links or subpages — use ONLY the exact base URLs listed here.\n\n"
        "VERIFIED RESOURCE URLs (use ONLY these):\n"
        "LEARNING PLATFORMS:\n"
        "- https://www.freecodecamp.org/ (type: course, Free coding curriculum)\n"
        "- https://www.codecademy.com/ (type: course, Interactive coding lessons)\n"
        "- https://www.khanacademy.org/ (type: course, Free courses on many subjects)\n"
        "- https://www.coursera.org/ (type: course, University courses online)\n"
        "- https://www.edx.org/ (type: course, University courses online)\n"
        "- https://www.udemy.com/ (type: course, Affordable video courses)\n"
        "- https://ocw.mit.edu/ (type: course, MIT free courseware)\n"
        "PROGRAMMING DOCS:\n"
        "- https://docs.python.org/3/tutorial/ (type: docs, Official Python tutorial)\n"
        "- https://developer.mozilla.org/en-US/ (type: docs, Web development docs)\n"
        "- https://www.w3schools.com/ (type: docs, Web development tutorials)\n"
        "- https://realpython.com/ (type: article, Python tutorials and guides)\n"
        "- https://javascript.info/ (type: docs, Modern JavaScript tutorial)\n"
        "- https://go.dev/doc/ (type: docs, Official Go documentation)\n"
        "- https://doc.rust-lang.org/book/ (type: docs, The Rust Programming Language book)\n"
        "- https://react.dev/ (type: docs, Official React documentation)\n"
        "PRACTICE:\n"
        "- https://leetcode.com/ (type: exercise, Coding interview practice)\n"
        "- https://exercism.org/ (type: exercise, Free coding exercises in 70+ languages)\n"
        "- https://www.hackerrank.com/ (type: exercise, Coding challenges)\n"
        "- https://projecteuler.net/ (type: exercise, Math + programming problems)\n"
        "- https://codewars.com/ (type: exercise, Code kata practice)\n"
        "TOOLS & REFERENCES:\n"
        "- https://github.com/ (type: tool, Code hosting and open source projects)\n"
        "- https://stackoverflow.com/ (type: tool, Q&A for developers)\n"
        "- https://www.youtube.com/ (type: video, Video tutorials — use base URL only)\n"
        "- https://medium.com/ (type: article, Tech articles and blogs)\n"
        "- https://dev.to/ (type: article, Developer community articles)\n"
        "GENERAL LEARNING:\n"
        "- https://www.duolingo.com/ (type: tool, Language learning)\n"
        "- https://brilliant.org/ (type: course, Math and science)\n"
        "- https://www.skillshare.com/ (type: course, Creative skills)\n"
        "- https://www.notion.so/ (type: tool, Note-taking and organization)\n"
        "- https://todoist.com/ (type: tool, Task management)\n\n"
        "Pick the most relevant 1-3 resources per task from this list. "
        "Use the EXACT URLs shown above. Never modify or guess at URLs."
    )
    user_prompt = ""
    if context:
        user_prompt += f"Background about the user:\n{context}\n\n"
    user_prompt += f"Goal: {goal_text}\nTime horizon (days): {horizon_days}\n\nReturn ONLY valid JSON that matches the provided schema."

    return await llm.generate_json(
        system=system,
        user=user_prompt,
        schema_name="goal_roadmap",
        schema=ROADMAP_SCHEMA,
        strict=True,
        temperature=0.3,
    )


INTAKE_QUESTIONS = [
    "What's your main goal? Tell me everything — what do you want to achieve and why it matters to you.",
    "What's your current level of experience with this? (complete beginner, some knowledge, intermediate, etc.)",
    "What usually blocks you or stops you from making progress on goals like this? (lack of time, motivation, not knowing where to start, etc.)",
    "How much time can you realistically dedicate per day? And do you have a deadline or target date in mind?",
]


async def run_intake_conversation(llm, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Drive a conversational intake to understand the user's goal deeply.
    Returns {"type": "question", "message": str} or {"type": "ready", "summary": str}
    """
    system = (
        "You are a warm, encouraging AI productivity coach having a conversation to understand the user's goal.\n\n"
        "Your job is to gather:\n"
        "1. WHAT they want to achieve (specific goal)\n"
        "2. WHY it matters to them\n"
        "3. Their current level / experience\n"
        "4. What usually blocks them (procrastination, confusion, lack of resources, etc.)\n"
        "5. How much time they have per day and any deadlines\n\n"
        "Ask ONE follow-up question at a time. Be conversational and supportive, not robotic.\n"
        "Once you have enough information (usually after 3-5 exchanges), respond with EXACTLY this format:\n"
        "READY_TO_PLAN: <a detailed summary paragraph of everything you learned about their goal, experience, blockers, and time constraints>\n\n"
        "Do NOT use that prefix until you genuinely have enough info. Keep questions short and natural."
    )

    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    reply = await llm.generate_text(system=system, user=conversation, temperature=0.7)

    if reply.strip().startswith("READY_TO_PLAN:"):
        summary = reply.strip()[len("READY_TO_PLAN:"):].strip()
        return {"type": "ready", "summary": summary}

    return {"type": "question", "message": reply.strip()}