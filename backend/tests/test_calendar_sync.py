"""Reconciling task records against Google Calendar."""

from datetime import datetime, timedelta

import pytest

from app.agents.calendar_sync import reconcile, sync_window
from app.db.models import TaskRecord

BASE = datetime(2026, 9, 15, 9, 0, 0)


def make_task(db, user_id, *, title="A task", start=BASE, minutes=60, event_id="evt-1", task_hash="h1"):
    task = TaskRecord(
        user_id=user_id,
        goal="Learn Rust",
        title=title,
        estimate_minutes=minutes,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=minutes) if start else None,
        calendar_event_id=event_id,
        task_hash=task_hash,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def event(event_id="evt-1", task_id="h1", start=BASE, minutes=60, **extra):
    body = {
        "id": event_id,
        "start": {"dateTime": start.isoformat() + "Z"},
        "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat() + "Z"},
        "extendedProperties": {"private": {"productivity_copilot_task_id": task_id}},
    }
    body.update(extra)
    return body


class TestSyncWindow:
    def test_none_when_nothing_is_scheduled(self):
        assert sync_window([]) is None

    def test_spans_all_tasks_with_padding(self, db, connected_user):
        make_task(db, connected_user.id, event_id="e1", task_hash="h1", start=BASE)
        make_task(db, connected_user.id, event_id="e2", task_hash="h2", start=BASE + timedelta(days=5))

        start, end = sync_window(db.query(TaskRecord).all())
        assert start < BASE
        assert end > BASE + timedelta(days=5)


class TestReconcile:
    def test_unchanged_event_leaves_the_task_alone(self, db, connected_user):
        task = make_task(db, connected_user.id)
        report = reconcile(db, [task], [event()])

        assert report.unchanged == 1
        assert report.moved == []
        assert report.removed == []
        assert task.scheduled_start == BASE

    def test_a_moved_event_updates_the_stored_time(self, db, connected_user):
        task = make_task(db, connected_user.id)
        moved_to = BASE + timedelta(hours=3)

        report = reconcile(db, [task], [event(start=moved_to)])

        assert len(report.moved) == 1
        assert report.moved[0]["title"] == "A task"
        assert task.scheduled_start == moved_to
        assert task.scheduled_end == moved_to + timedelta(minutes=60)

    def test_a_resized_event_updates_the_estimate(self, db, connected_user):
        task = make_task(db, connected_user.id, minutes=60)

        reconcile(db, [task], [event(minutes=90)])

        assert task.estimate_minutes == 90

    def test_a_deleted_event_unschedules_the_task_but_keeps_it(self, db, connected_user):
        task = make_task(db, connected_user.id)

        report = reconcile(db, [task], [])

        assert len(report.removed) == 1
        assert task.calendar_event_id is None
        assert task.scheduled_start is None
        # The task itself survives — the user still owes the work.
        assert db.query(TaskRecord).filter(TaskRecord.id == task.id).first() is not None
        assert task.status == "pending"

    def test_a_cancelled_event_counts_as_deleted(self, db, connected_user):
        task = make_task(db, connected_user.id)

        report = reconcile(db, [task], [event(status="cancelled")])

        assert len(report.removed) == 1
        assert task.calendar_event_id is None

    def test_sub_minute_drift_is_not_reported_as_a_move(self, db, connected_user):
        """Google echoes times back with its own precision."""
        task = make_task(db, connected_user.id)

        reconcile(db, [task], [event(start=BASE + timedelta(seconds=20))])

        assert task.scheduled_start == BASE

    def test_matches_by_task_id_when_the_event_id_changed(self, db, connected_user):
        """Google can recreate an event with a new id; the stamped task id persists."""
        task = make_task(db, connected_user.id, event_id="old-id", task_hash="h1")

        reconcile(db, [task], [event(event_id="brand-new-id", task_id="h1")])

        assert task.calendar_event_id == "brand-new-id"

    def test_all_day_events_are_left_alone(self, db, connected_user):
        task = make_task(db, connected_user.id)
        all_day = {
            "id": "evt-1",
            "start": {"date": "2026-09-15"},
            "end": {"date": "2026-09-16"},
            "extendedProperties": {"private": {"productivity_copilot_task_id": "h1"}},
        }

        report = reconcile(db, [task], [all_day])

        assert report.unchanged == 1
        assert task.scheduled_start == BASE

    def test_tasks_with_no_event_are_skipped_not_checked(self, db, connected_user):
        task = make_task(db, connected_user.id, event_id=None)

        report = reconcile(db, [task], [])

        assert report.skipped == 1
        assert report.checked == 0

    def test_last_synced_at_is_stamped(self, db, connected_user):
        task = make_task(db, connected_user.id)
        assert task.last_synced_at is None

        reconcile(db, [task], [event()])

        assert task.last_synced_at is not None

    def test_summary_reads_sensibly(self, db, connected_user):
        task = make_task(db, connected_user.id)
        assert "Everything matches" in reconcile(db, [task], [event()]).as_dict()["summary"]


@pytest.fixture
def calendar_stub(monkeypatch):
    state = {"events": [], "updated": [], "deleted": []}

    monkeypatch.setattr("app.api.routes.tasks.ensure_fresh_token", lambda db, row: row.token_json)
    monkeypatch.setattr("app.api.routes.tasks.list_events", lambda *a, **kw: state["events"])
    monkeypatch.setattr(
        "app.api.routes.tasks.update_event",
        lambda eid, s, e, tz, **kw: state["updated"].append((eid, s, e)) or {"id": eid, "htmlLink": "x"},
    )
    monkeypatch.setattr(
        "app.api.routes.tasks.delete_event",
        lambda eid, **kw: state["deleted"].append(eid) or True,
    )
    return state


class TestSyncEndpoint:
    def test_requires_auth(self, client):
        assert client.post("/tasks/sync").status_code == 401

    def test_reports_a_moved_event(self, auth_client, connected_user, db, calendar_stub):
        make_task(db, connected_user.id)
        calendar_stub["events"] = [event(start=BASE + timedelta(hours=2))]

        body = auth_client.post("/tasks/sync").json()

        assert body["checked"] == 1
        assert len(body["moved"]) == 1
        assert "moved" in body["summary"]

    def test_reports_a_removed_event(self, auth_client, connected_user, db, calendar_stub):
        make_task(db, connected_user.id)
        calendar_stub["events"] = []

        body = auth_client.post("/tasks/sync").json()

        assert len(body["removed"]) == 1
        assert "no longer on your calendar" in body["summary"]

    def test_nothing_scheduled_is_not_an_error(self, auth_client, connected_user, calendar_stub):
        body = auth_client.post("/tasks/sync").json()
        assert body["checked"] == 0


class TestRescheduleEndpoint:
    def test_requires_auth(self, client):
        assert client.patch("/tasks/1/reschedule", json={
            "start": BASE.isoformat(), "end": (BASE + timedelta(hours=1)).isoformat()
        }).status_code == 401

    def test_moves_the_task_and_the_calendar_event(
        self, auth_client, connected_user, db, calendar_stub
    ):
        task = make_task(db, connected_user.id)
        new_start = BASE + timedelta(days=1)

        resp = auth_client.patch(f"/tasks/{task.id}/reschedule", json={
            "start": new_start.isoformat(),
            "end": (new_start + timedelta(minutes=90)).isoformat(),
        })

        assert resp.status_code == 200
        assert resp.json()["estimate_minutes"] == 90
        assert len(calendar_stub["updated"]) == 1, "the calendar was not updated"

        db.expire_all()
        assert db.get(TaskRecord, task.id).scheduled_start == new_start

    def test_rejects_an_end_before_the_start(self, auth_client, connected_user, db, calendar_stub):
        task = make_task(db, connected_user.id)

        resp = auth_client.patch(f"/tasks/{task.id}/reschedule", json={
            "start": BASE.isoformat(),
            "end": (BASE - timedelta(hours=1)).isoformat(),
        })
        assert resp.status_code == 422

    def test_another_users_task_is_not_found(self, auth_client, connected_user, db, calendar_stub):
        from app.db.models import UserProfile

        other = UserProfile(email="someone-else@example.com")
        db.add(other)
        db.commit()
        db.refresh(other)
        theirs = make_task(db, other.id, event_id="evt-other", task_hash="h-other")

        resp = auth_client.patch(f"/tasks/{theirs.id}/reschedule", json={
            "start": BASE.isoformat(), "end": (BASE + timedelta(hours=1)).isoformat(),
        })
        assert resp.status_code == 404

    def test_the_db_is_not_updated_when_google_rejects_the_move(
        self, auth_client, connected_user, db, monkeypatch, calendar_stub
    ):
        task = make_task(db, connected_user.id)

        def boom(*a, **kw):
            raise RuntimeError("Google said no")

        monkeypatch.setattr("app.api.routes.tasks.update_event", boom)

        resp = auth_client.patch(f"/tasks/{task.id}/reschedule", json={
            "start": (BASE + timedelta(days=2)).isoformat(),
            "end": (BASE + timedelta(days=2, hours=1)).isoformat(),
        })

        assert resp.status_code == 502
        db.expire_all()
        assert db.get(TaskRecord, task.id).scheduled_start == BASE, "stored a time the calendar doesn't have"


class TestDeleteEndpoint:
    def test_requires_auth(self, client):
        assert client.delete("/tasks/1").status_code == 401

    def test_removes_the_task_and_its_event(self, auth_client, connected_user, db, calendar_stub):
        task = make_task(db, connected_user.id)

        resp = auth_client.delete(f"/tasks/{task.id}")

        assert resp.status_code == 200
        assert resp.json()["calendar_event_removed"] is True
        assert calendar_stub["deleted"] == ["evt-1"]
        assert db.query(TaskRecord).filter(TaskRecord.id == task.id).first() is None

    def test_the_row_still_goes_when_the_calendar_call_fails(
        self, auth_client, connected_user, db, monkeypatch, calendar_stub
    ):
        task = make_task(db, connected_user.id)

        def boom(*a, **kw):
            raise RuntimeError("Google is down")

        monkeypatch.setattr("app.api.routes.tasks.delete_event", boom)

        resp = auth_client.delete(f"/tasks/{task.id}")

        assert resp.status_code == 200
        assert resp.json()["calendar_event_removed"] is False
        assert db.query(TaskRecord).filter(TaskRecord.id == task.id).first() is None

    def test_another_users_task_is_not_found(self, auth_client, connected_user, db, calendar_stub):
        from app.db.models import UserProfile

        other = UserProfile(email="someone-else@example.com")
        db.add(other)
        db.commit()
        db.refresh(other)
        theirs = make_task(db, other.id, event_id="evt-other", task_hash="h-other")

        assert auth_client.delete(f"/tasks/{theirs.id}").status_code == 404
        assert db.query(TaskRecord).filter(TaskRecord.id == theirs.id).first() is not None
