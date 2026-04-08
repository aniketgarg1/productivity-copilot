"""AI agent that generates check-in call scripts and processes user responses."""

from __future__ import annotations

from typing import Any, Dict, List

from app.llm.factory import get_llm


async def generate_checkin_greeting(
    user_name: str | None,
    tasks: List[Dict[str, Any]],
) -> str:
    """Build the opening message for a daily check-in call."""
    llm = get_llm()

    pending = [t for t in tasks if t["status"] in ("pending", "in_progress")]
    completed = [t for t in tasks if t["status"] == "done"]

    name = user_name or "there"

    task_summary = ""
    if pending:
        lines = [f"- {t['title']} ({t['estimate_minutes']} min, status: {t['status']})" for t in pending]
        task_summary += "Tasks still to do:\n" + "\n".join(lines)
    if completed:
        lines = [f"- {t['title']}" for t in completed]
        task_summary += "\n\nTasks already completed:\n" + "\n".join(lines)

    if not pending and not completed:
        task_summary = "No tasks scheduled for today."

    system = (
        "You are an encouraging, warm AI productivity coach calling the user for their daily check-in. "
        "Keep it concise — this is a phone call, not an essay. "
        "If they have pending tasks, ask how they're doing on each one and if they need help. "
        "If they've completed tasks, celebrate their progress. "
        "If nothing is done, gently motivate them without being pushy. "
        "Speak naturally as if talking to a friend. Use short sentences."
    )
    user_prompt = f"""
User's name: {name}

{task_summary}

Generate a short, warm phone greeting (2-4 sentences) that:
1. Greets them by name
2. Mentions their tasks for today
3. Asks for an update
"""
    return await llm.generate_text(system=system, user=user_prompt, temperature=0.7)


async def generate_followup(
    user_name: str | None,
    user_speech: str,
    tasks: List[Dict[str, Any]],
    previous_ai_message: str,
) -> str:
    """Process the user's spoken response and generate a follow-up."""
    llm = get_llm()
    name = user_name or "there"

    task_lines = "\n".join(
        f"- {t['title']} (status: {t['status']})" for t in tasks
    )

    system = (
        "You are a warm AI productivity coach on a phone call. "
        "The user just responded to your check-in. "
        "Acknowledge what they said, provide encouragement, and give a brief motivational close. "
        "If they seem stuck, offer a small actionable suggestion. "
        "Keep it to 2-3 sentences — this is a phone call."
    )
    user_prompt = f"""
User's name: {name}

Their tasks:
{task_lines}

Your previous message: {previous_ai_message}

What the user just said: "{user_speech}"

Respond naturally. Be encouraging and concise.
"""
    return await llm.generate_text(system=system, user=user_prompt, temperature=0.7)


async def generate_motivation(
    user_name: str | None,
    tasks: List[Dict[str, Any]],
) -> str:
    """Generate a motivational message when the user hasn't made progress."""
    llm = get_llm()
    name = user_name or "there"

    overdue = [t for t in tasks if t["status"] == "pending"]
    task_lines = "\n".join(f"- {t['title']}" for t in overdue) if overdue else "No specific tasks."

    system = (
        "You are a caring AI productivity coach. The user hasn't made progress on their tasks. "
        "Don't guilt-trip them. Instead: "
        "1. Normalize that everyone has off days "
        "2. Suggest picking just ONE small task to start with "
        "3. Remind them why they set this goal "
        "Keep it to 3-4 warm, encouraging sentences for a phone call."
    )
    user_prompt = f"""
User's name: {name}

Tasks they haven't started:
{task_lines}

Generate a gentle, motivating phone message.
"""
    return await llm.generate_text(system=system, user=user_prompt, temperature=0.8)
