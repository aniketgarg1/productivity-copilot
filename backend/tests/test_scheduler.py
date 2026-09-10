"""Slot building and first-fit scheduling."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.agents.scheduler import (
    Task,
    build_free_slots,
    flatten_tasks,
    schedule_tasks_into_slots,
)
from tests.conftest import roadmap_fixture

TZ = "America/Phoenix"


def _slot(day_offset: int, start_hour: int, end_hour: int):
    tz = ZoneInfo(TZ)
    day = datetime.now(tz).date() + timedelta(days=day_offset)
    return (
        datetime.combine(day, datetime.min.time(), tzinfo=tz).replace(hour=start_hour),
        datetime.combine(day, datetime.min.time(), tzinfo=tz).replace(hour=end_hour),
    )


def _task(title, minutes, milestone="M", index=0):
    return Task(title=title, minutes=minutes, notes="", milestone_title=milestone, index=index)


class TestFlattenTasks:
    def test_carries_milestone_and_position(self):
        tasks = flatten_tasks(roadmap_fixture())

        assert [t.title for t in tasks] == [
            "Read the Book ch. 4",
            "Exercism exercises",
            "Read the Book ch. 4",
            "Build the whole CLI",
        ]
        # Same title, different milestone — the fields that disambiguate them
        # must actually differ, or their task ids collide.
        assert tasks[0].milestone_title == "Ownership"
        assert tasks[2].milestone_title == "Ship something"
        assert tasks[0].index != tasks[2].index

    def test_resources_survive(self):
        tasks = flatten_tasks(roadmap_fixture())
        assert tasks[0].resources[0]["url"] == "https://doc.rust-lang.org/book/"
        assert tasks[1].resources == []


class TestScheduleTasksIntoSlots:
    def test_does_not_mutate_the_callers_list(self):
        tasks = [_task("a", 30), _task("b", 30)]
        schedule_tasks_into_slots(tasks, [_slot(1, 9, 17)], TZ, max_daily_minutes=120)
        assert len(tasks) == 2, "input list was consumed"

    def test_respects_the_daily_cap(self):
        tasks = [_task(f"t{i}", 60, index=i) for i in range(4)]
        scheduled, unscheduled = schedule_tasks_into_slots(
            tasks, [_slot(1, 9, 18)], TZ, max_daily_minutes=120
        )
        # One 9-hour slot, but only 2 hours a day allowed.
        assert len(scheduled) == 2
        assert len(unscheduled) == 2

    def test_spreads_across_days(self):
        tasks = [_task(f"t{i}", 60, index=i) for i in range(4)]
        slots = [_slot(d, 9, 18) for d in range(1, 4)]
        scheduled, unscheduled = schedule_tasks_into_slots(tasks, slots, TZ, max_daily_minutes=120)

        assert len(scheduled) == 4
        assert unscheduled == []
        days = {s["start"].date() for s in scheduled}
        assert len(days) == 2, "4x60m at 120m/day should occupy exactly two days"

    def test_task_longer_than_the_daily_cap_is_still_scheduled(self):
        """Regression: a 300m task under a 120m/day cap used to vanish silently."""
        tasks = [_task("huge", 300)]
        scheduled, unscheduled = schedule_tasks_into_slots(
            tasks, [_slot(1, 8, 18)], TZ, max_daily_minutes=120
        )
        assert unscheduled == []
        assert len(scheduled) == 1
        assert (scheduled[0]["end"] - scheduled[0]["start"]) == timedelta(minutes=300)

    def test_oversized_task_reported_when_no_slot_is_long_enough(self):
        tasks = [_task("huge", 300)]
        scheduled, unscheduled = schedule_tasks_into_slots(
            tasks, [_slot(1, 9, 11)], TZ, max_daily_minutes=600
        )
        assert scheduled == []
        assert [t.title for t in unscheduled] == ["huge"]

    def test_scheduled_blocks_never_overlap(self):
        tasks = [_task(f"t{i}", 45, index=i) for i in range(6)]
        slots = [_slot(d, 9, 18) for d in range(1, 5)]
        scheduled, _ = schedule_tasks_into_slots(tasks, slots, TZ, max_daily_minutes=180)

        ordered = sorted(scheduled, key=lambda s: s["start"])
        for earlier, later in zip(ordered, ordered[1:]):
            assert later["start"] >= earlier["end"], "two tasks overlap in time"

    def test_carries_task_id_through(self):
        t = _task("a", 30)
        t.task_id = "abc123"
        scheduled, _ = schedule_tasks_into_slots([t], [_slot(1, 9, 17)], TZ)
        assert scheduled[0]["task_id"] == "abc123"


class TestBuildFreeSlots:
    def test_queries_freebusy_once_not_once_per_day(self):
        """Regression: this used to issue one API call per day in the horizon."""
        calls = []

        def fake_freebusy(token_json, tmin, tmax):
            calls.append((tmin, tmax))
            return {"calendars": {"primary": {"busy": []}}}

        build_free_slots(fake_freebusy, "{}", horizon_days=30, timezone=TZ)
        assert len(calls) == 1, f"expected 1 batched call, got {len(calls)}"

    def test_chunks_very_long_horizons(self):
        calls = []

        def fake_freebusy(token_json, tmin, tmax):
            calls.append((tmin, tmax))
            return {"calendars": {"primary": {"busy": []}}}

        build_free_slots(fake_freebusy, "{}", horizon_days=180, timezone=TZ)
        assert 1 < len(calls) <= 4

    def test_skips_holidays(self):
        tz = ZoneInfo(TZ)
        today = datetime.now(tz).date()
        holiday = (today + timedelta(days=1)).isoformat()

        def fake_freebusy(token_json, tmin, tmax):
            return {"calendars": {"primary": {"busy": []}}}

        slots = build_free_slots(
            fake_freebusy, "{}", horizon_days=4, timezone=TZ, holidays=[holiday]
        )
        assert all(s[0].date().isoformat() != holiday for s in slots)

    def test_never_returns_a_slot_in_the_past(self):
        """Regression: today's slots used to start at WORKDAY_START_HOUR regardless of now."""
        def fake_freebusy(token_json, tmin, tmax):
            return {"calendars": {"primary": {"busy": []}}}

        now = datetime.now(ZoneInfo(TZ))
        slots = build_free_slots(fake_freebusy, "{}", horizon_days=3, timezone=TZ)
        assert all(s[0] >= now - timedelta(seconds=5) for s in slots)

    def test_busy_time_is_excluded(self):
        tz = ZoneInfo(TZ)
        tomorrow = datetime.now(tz).date() + timedelta(days=1)
        busy_start = datetime.combine(tomorrow, datetime.min.time(), tzinfo=tz).replace(hour=10)
        busy_end = busy_start + timedelta(hours=2)

        def fake_freebusy(token_json, tmin, tmax):
            return {
                "calendars": {
                    "primary": {
                        "busy": [{"start": busy_start.isoformat(), "end": busy_end.isoformat()}]
                    }
                }
            }

        slots = build_free_slots(fake_freebusy, "{}", horizon_days=2, timezone=TZ)
        tomorrow_slots = [s for s in slots if s[0].date() == tomorrow]

        for start, end in tomorrow_slots:
            assert not (start < busy_end and end > busy_start), "slot overlaps a busy block"

    @pytest.mark.parametrize("horizon", [1, 7, 30])
    def test_slots_stay_inside_work_hours(self, horizon):
        def fake_freebusy(token_json, tmin, tmax):
            return {"calendars": {"primary": {"busy": []}}}

        slots = build_free_slots(fake_freebusy, "{}", horizon_days=horizon, timezone=TZ)
        for start, end in slots:
            assert start.hour >= 9 or start.date() == datetime.now(ZoneInfo(TZ)).date()
            assert end.hour <= 18
            assert start < end
