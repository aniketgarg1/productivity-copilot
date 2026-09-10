"""Reconcile stored task records against what is actually on Google Calendar.

The DB and the calendar drift apart as soon as the user drags an event to a new
time or deletes it. Nothing else in the app notices, so scheduled_start goes
stale and check-in calls talk about tasks at the wrong time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.db.models import TaskRecord
from app.tools.google_calendar import event_task_id, parse_event_times

logger = logging.getLogger(__name__)

# How far either side of the stored tasks to look for their events.
WINDOW_PADDING = timedelta(days=1)

# Ignore sub-minute differences: Google echoes times back with its own precision.
DRIFT_TOLERANCE = timedelta(seconds=60)


@dataclass
class SyncReport:
    checked: int = 0
    unchanged: int = 0
    moved: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    skipped: int = 0

    def as_dict(self) -> dict:
        return {
            "checked": self.checked,
            "unchanged": self.unchanged,
            "moved": self.moved,
            "removed": self.removed,
            "skipped_no_event": self.skipped,
            "summary": self._summary(),
        }

    def _summary(self) -> str:
        if not self.checked:
            return "No scheduled tasks to check."
        parts = [f"Checked {self.checked} task(s)."]
        if self.moved:
            parts.append(f"{len(self.moved)} moved in your calendar.")
        if self.removed:
            parts.append(f"{len(self.removed)} no longer on your calendar.")
        if not self.moved and not self.removed:
            parts.append("Everything matches.")
        return " ".join(parts)


def _to_naive_utc(dt: datetime) -> datetime:
    """Stored timestamps are naive; compare in one frame."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def sync_window(tasks: Iterable[TaskRecord]) -> tuple[datetime, datetime] | None:
    """The time range worth querying for a set of tasks."""
    starts = [t.scheduled_start for t in tasks if t.scheduled_start]
    ends = [t.scheduled_end for t in tasks if t.scheduled_end]
    if not starts:
        return None
    return min(starts) - WINDOW_PADDING, max(ends or starts) + WINDOW_PADDING


def reconcile(db, tasks: list[TaskRecord], events: list[dict]) -> SyncReport:
    """
    Apply what the calendar says to the stored tasks.

    * event moved   -> stored times are updated
    * event deleted -> the row is detached from the calendar and unscheduled,
                       keeping the task itself (and its status) intact
    """
    report = SyncReport()

    by_task_id = {}
    by_event_id = {}
    for ev in events:
        if ev.get("status") == "cancelled":
            continue
        if tid := event_task_id(ev):
            by_task_id[tid] = ev
        if eid := ev.get("id"):
            by_event_id[eid] = ev

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for task in tasks:
        if not task.calendar_event_id:
            report.skipped += 1
            continue

        report.checked += 1

        event = by_task_id.get(task.task_hash) or by_event_id.get(task.calendar_event_id)

        if event is None:
            report.removed.append({"id": task.id, "title": task.title})
            task.calendar_event_id = None
            task.scheduled_start = None
            task.scheduled_end = None
            task.last_synced_at = now
            continue

        start, end = parse_event_times(event)
        if start is None or end is None:
            # An all-day event carries no time to sync to.
            report.unchanged += 1
            task.last_synced_at = now
            continue

        new_start, new_end = _to_naive_utc(start), _to_naive_utc(end)
        old_start, old_end = task.scheduled_start, task.scheduled_end

        drifted = (
            old_start is None
            or old_end is None
            or abs(new_start - old_start) > DRIFT_TOLERANCE
            or abs(new_end - old_end) > DRIFT_TOLERANCE
        )

        if drifted:
            report.moved.append({
                "id": task.id,
                "title": task.title,
                "from": old_start.isoformat() if old_start else None,
                "to": new_start.isoformat(),
            })
            task.scheduled_start = new_start
            task.scheduled_end = new_end
            task.estimate_minutes = max(1, int((new_end - new_start).total_seconds() // 60))
        else:
            report.unchanged += 1

        # Keep the id fresh in case the event was recreated by Google.
        task.calendar_event_id = event.get("id") or task.calendar_event_id
        task.last_synced_at = now

    db.commit()
    return report
