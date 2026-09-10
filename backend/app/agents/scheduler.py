from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time, date
from typing import List, Tuple, Dict, Any
from zoneinfo import ZoneInfo

from app.core.config import settings

UTC = ZoneInfo("UTC")

# Google's free/busy query degrades over very long ranges, so ask in chunks.
FREEBUSY_CHUNK_DAYS = 60


@dataclass
class Task:
    title: str
    minutes: int
    notes: str
    milestone_title: str = ""
    index: int = 0
    resources: List[Dict[str, Any]] = field(default_factory=list)
    task_id: str | None = None


def _parse_busy(resp: Dict[str, Any]) -> List[Tuple[datetime, datetime]]:
    busy = []
    cal = resp.get("calendars", {}).get("primary", {})
    for b in cal.get("busy", []):
        # Google returns ISO with timezone offsets
        start = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
        busy.append((start, end))
    busy.sort(key=lambda x: x[0])
    return busy


def _merge(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not intervals:
        return []
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def _day_bounds(d: date, tz: ZoneInfo) -> Tuple[datetime, datetime]:
    start = datetime.combine(d, time(settings.WORKDAY_START_HOUR, 0), tzinfo=tz)
    end = datetime.combine(d, time(settings.WORKDAY_END_HOUR, 0), tzinfo=tz)
    return start, end


def _free_slots_for_day(
    day_start: datetime,
    day_end: datetime,
    busy: List[Tuple[datetime, datetime]],
    padding: timedelta,
) -> List[Tuple[datetime, datetime]]:
    # Clip busy intervals to the workday window
    clipped = []
    for s, e in busy:
        if e <= day_start or s >= day_end:
            continue
        clipped.append((max(s, day_start), min(e, day_end)))
    clipped = _merge(sorted(clipped, key=lambda x: x[0]))

    slots = []
    cur = day_start
    for s, e in clipped:
        if s - cur >= padding:
            slots.append((cur, s))
        cur = max(cur, e)
    if day_end - cur >= padding:
        slots.append((cur, day_end))
    return slots


def flatten_tasks(roadmap: Dict[str, Any]) -> List[Task]:
    tasks: List[Task] = []
    for ms in roadmap.get("milestones", []):
        for t in ms.get("tasks", []):
            tasks.append(
                Task(
                    title=t["title"],
                    minutes=int(t["estimate_minutes"]),
                    notes=t.get("notes", "") or "",
                    milestone_title=ms.get("title", "") or "",
                    index=len(tasks),
                    resources=t.get("resources", []) or [],
                )
            )
    return tasks


def schedule_tasks_into_slots(
    tasks: List[Task],
    free_slots_by_day: List[Tuple[datetime, datetime]],
    timezone: str,
    max_daily_minutes: int = 120,
) -> Tuple[List[Dict[str, Any]], List[Task]]:
    """
    First-fit scheduling with a daily time cap.
    Spreads tasks across days so users aren't overloaded.

    Returns (scheduled, unscheduled). The caller's ``tasks`` list is not modified.
    """
    tz = ZoneInfo(timezone)
    padding = timedelta(minutes=settings.SLOT_PADDING_MINUTES)

    pending = list(tasks)  # never mutate the caller's list
    scheduled: List[Dict[str, Any]] = []
    slot_idx = 0
    cur_start = None
    daily_used: Dict[date, int] = {}

    while pending and slot_idx < len(free_slots_by_day):
        slot_start, slot_end = free_slots_by_day[slot_idx]
        slot_start = slot_start.astimezone(tz)
        slot_end = slot_end.astimezone(tz)

        current_day = slot_start.date()
        used_today = daily_used.get(current_day, 0)

        # Day already at capacity — move on.
        if used_today >= max_daily_minutes:
            slot_idx += 1
            cur_start = None
            continue

        if cur_start is None or cur_start < slot_start:
            cur_start = slot_start

        if cur_start >= slot_end:
            slot_idx += 1
            cur_start = None
            continue

        task = pending[0]
        task_end = cur_start + timedelta(minutes=task.minutes)

        # A task longer than the whole daily budget would otherwise never fit and
        # be dropped silently, so allow it to start a fresh, otherwise-empty day.
        fits_budget = (
            used_today == 0
            or task.minutes <= max_daily_minutes - used_today
        )
        if not fits_budget:
            slot_idx += 1
            cur_start = None
            continue

        if task_end <= slot_end:
            scheduled.append({
                "title": task.title,
                "notes": task.notes,
                "resources": task.resources,
                "milestone_title": task.milestone_title,
                "task_id": task.task_id,
                "start": cur_start,
                "end": task_end,
            })
            daily_used[current_day] = used_today + task.minutes
            pending.pop(0)
            cur_start = task_end + padding
        else:
            slot_idx += 1
            cur_start = None

    return scheduled, pending


def build_free_slots(
    freebusy_func,
    token_json: str,
    horizon_days: int,
    timezone: str,
    holidays: List[str] | None = None,
) -> List[Tuple[datetime, datetime]]:
    """
    Returns a flat list of free slots across days inside work hours.
    holidays: list of YYYY-MM-DD strings to skip

    Busy times are fetched in large chunks rather than one request per day —
    a 30-day horizon used to cost 30 round-trips to the Google Calendar API.
    """
    tz = ZoneInfo(timezone)
    holidays_set = set(holidays or [])

    today = datetime.now(tz).date()
    padding = timedelta(minutes=settings.SLOT_PADDING_MINUTES)

    days = [
        today + timedelta(days=i)
        for i in range(horizon_days)
        if (today + timedelta(days=i)).isoformat() not in holidays_set
    ]
    if not days:
        return []

    # One free/busy request per chunk of days, then slice the result per day.
    busy_all: List[Tuple[datetime, datetime]] = []
    for i in range(0, len(days), FREEBUSY_CHUNK_DAYS):
        chunk = days[i:i + FREEBUSY_CHUNK_DAYS]
        window_start, _ = _day_bounds(chunk[0], tz)
        _, window_end = _day_bounds(chunk[-1], tz)
        resp = freebusy_func(
            token_json,
            window_start.astimezone(UTC).isoformat(),
            window_end.astimezone(UTC).isoformat(),
        )
        busy_all.extend(_parse_busy(resp))

    busy_all = _merge(sorted(busy_all, key=lambda x: x[0]))

    now = datetime.now(tz)
    all_slots: List[Tuple[datetime, datetime]] = []
    for d in days:
        day_start, day_end = _day_bounds(d, tz)
        # Never hand back a slot that has already passed — today's workday may
        # be half over by the time the user asks for a plan.
        day_start = max(day_start, now)
        if day_start >= day_end:
            continue
        day_busy = [b for b in busy_all if b[1] > day_start and b[0] < day_end]
        all_slots.extend(_free_slots_for_day(day_start, day_end, day_busy, padding))

    return all_slots
