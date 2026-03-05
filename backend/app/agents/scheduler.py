from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time, date
from typing import List, Tuple, Dict, Any
from zoneinfo import ZoneInfo

from app.core.config import settings


@dataclass
class Task:
    title: str
    minutes: int
    notes: str


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
            tasks.append(Task(
                title=t["title"],
                minutes=int(t["estimate_minutes"]),
                notes=t.get("notes", ""),
            ))
    return tasks


def schedule_tasks_into_slots(
    tasks: List[Task],
    free_slots_by_day: List[Tuple[datetime, datetime]],
    timezone: str,
) -> List[Dict[str, Any]]:
    """
    First-fit: take earliest free slot, place tasks sequentially.
    Adds SLOT_PADDING_MINUTES between tasks.
    """
    tz = ZoneInfo(timezone)
    padding = timedelta(minutes=settings.SLOT_PADDING_MINUTES)

    scheduled = []
    slot_idx = 0
    cur_start = None

    while tasks and slot_idx < len(free_slots_by_day):
        slot_start, slot_end = free_slots_by_day[slot_idx]
        slot_start = slot_start.astimezone(tz)
        slot_end = slot_end.astimezone(tz)

        if cur_start is None or cur_start < slot_start:
            cur_start = slot_start

        # if no room, move to next slot
        if cur_start >= slot_end:
            slot_idx += 1
            cur_start = None
            continue

        task = tasks[0]
        dur = timedelta(minutes=task.minutes)
        task_end = cur_start + dur

        if task_end <= slot_end:
            scheduled.append({
                "title": task.title,
                "notes": task.notes,
                "start": cur_start,
                "end": task_end,
            })
            tasks.pop(0)
            cur_start = task_end + padding
        else:
            # task doesn't fit this slot -> next slot
            slot_idx += 1
            cur_start = None

    return scheduled


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
    """
    tz = ZoneInfo(timezone)
    holidays_set = set(holidays or [])

    today = datetime.now(tz).date()
    padding = timedelta(minutes=settings.SLOT_PADDING_MINUTES)

    all_slots: List[Tuple[datetime, datetime]] = []

    for i in range(horizon_days):
        d = today + timedelta(days=i)
        if d.isoformat() in holidays_set:
            continue

        day_start, day_end = _day_bounds(d, tz)

        # Query busy for just this day window
        resp = freebusy_func(
            token_json,
            day_start.astimezone(ZoneInfo("UTC")).isoformat(),
            day_end.astimezone(ZoneInfo("UTC")).isoformat(),
        )
        busy = _parse_busy(resp)
        slots = _free_slots_for_day(day_start, day_end, busy, padding)
        all_slots.extend(slots)

    return all_slots