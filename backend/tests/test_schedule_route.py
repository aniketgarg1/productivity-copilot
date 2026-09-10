"""End-to-end behaviour of POST /goals/schedule."""

from unittest.mock import patch

import pytest

from app.db.models import TaskRecord
from tests.conftest import FakeLLM, roadmap_fixture


@pytest.fixture
def calendar(monkeypatch):
    """Stub out Google Calendar and the LLM for the schedule route."""
    state = {"created": [], "freebusy_calls": [], "existing": []}

    def fake_freebusy(token_json, tmin, tmax):
        state["freebusy_calls"].append((tmin, tmax))
        return {"calendars": {"primary": {"busy": []}}}

    def fake_create_event(**kwargs):
        state["created"].append(kwargs)
        return {"id": f"evt-{len(state['created'])}", "htmlLink": "https://calendar.example/e"}

    patches = [
        patch("app.api.routes.schedule.get_llm", lambda: FakeLLM(json_result=roadmap_fixture())),
        patch("app.api.routes.schedule.freebusy", fake_freebusy),
        patch("app.api.routes.schedule.create_event", fake_create_event),
        patch("app.api.routes.schedule.list_events", lambda *a, **kw: state["existing"]),
        patch("app.api.routes.schedule.build_calendar_service", lambda tj: object()),
        patch("app.api.routes.schedule.ensure_fresh_token", lambda db, row: row.token_json),
    ]
    for p in patches:
        p.start()
    yield state
    for p in patches:
        p.stop()


def _post(client, **overrides):
    body = {"goal": "Learn Rust", "horizon_days": 30, "daily_hours": 2}
    body.update(overrides)
    return client.post("/goals/schedule", json=body)


class TestScheduleGoal:
    def test_requires_authentication(self, client, calendar):
        assert _post(client).status_code == 401

    def test_requires_a_connected_google_account(self, auth_client, calendar):
        resp = _post(auth_client)
        assert resp.status_code == 401
        assert "No Google account connected" in resp.json()["detail"]

    def test_duplicate_task_titles_do_not_crash(self, auth_client, connected_user, calendar):
        """Regression: repeated titles collided on task_hash and 500'd the request."""
        resp = _post(auth_client)

        assert resp.status_code == 200, resp.text
        titles = [e["title"] for e in resp.json()["events"]]
        assert titles.count("Read the Book ch. 4") == 2, "the repeated title was dropped"

    def test_task_ids_are_unique_across_milestones(self, auth_client, connected_user, calendar):
        resp = _post(auth_client)
        ids = [e["task_id"] for e in resp.json()["events"]]
        assert len(ids) == len(set(ids)), "two tasks share a task_id"

    def test_oversized_task_is_scheduled_not_dropped(self, auth_client, connected_user, calendar):
        """The 300-minute task exceeds the 120 min/day budget."""
        resp = _post(auth_client, daily_hours=2)
        titles = [e["title"] for e in resp.json()["events"]]
        assert "Build the whole CLI" in titles

    def test_freebusy_is_queried_once(self, auth_client, connected_user, calendar):
        _post(auth_client, horizon_days=30)
        assert len(calendar["freebusy_calls"]) == 1

    def test_task_records_are_persisted(self, auth_client, connected_user, calendar, db):
        _post(auth_client)

        records = db.query(TaskRecord).all()
        assert len(records) == 4
        assert all(r.user_id == connected_user.id for r in records)
        assert all(r.status == "pending" for r in records)
        assert all(r.calendar_event_id for r in records)

    def test_resources_are_stored_and_put_in_the_description(
        self, auth_client, connected_user, calendar, db
    ):
        _post(auth_client)

        record = db.query(TaskRecord).filter(TaskRecord.title == "Read the Book ch. 4").first()
        assert record.resources_json
        assert record.resources_json[0]["url"] == "https://doc.rust-lang.org/book/"

        with_resources = [c for c in calendar["created"] if "doc.rust-lang.org" in c["description"]]
        assert with_resources, "resource links never reached the calendar event"

    def test_rerunning_the_same_goal_is_idempotent(
        self, auth_client, connected_user, calendar, db
    ):
        first = _post(auth_client)
        assert len(first.json()["events"]) == 4

        second = _post(auth_client)
        assert second.status_code == 200
        assert second.json()["events"] == []
        assert "already scheduled" in second.json()["message"]
        assert db.query(TaskRecord).count() == 4, "re-running duplicated task records"

    def test_tasks_already_on_the_calendar_are_skipped(
        self, auth_client, connected_user, calendar
    ):
        first = _post(auth_client)
        existing_id = first.json()["events"][0]["task_id"]

        # Simulate that event still living on the user's calendar.
        calendar["existing"] = [
            {"extendedProperties": {"private": {"productivity_copilot_task_id": existing_id}}}
        ]
        calendar["created"].clear()

        second = _post(auth_client)
        assert existing_id not in [e["task_id"] for e in second.json()["events"]]

    def test_a_failing_calendar_insert_does_not_abort_the_whole_plan(
        self, auth_client, connected_user, calendar, db
    ):
        calls = {"n": 0}

        def flaky_create(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("Google said no")
            return {"id": f"evt-{calls['n']}", "htmlLink": "https://calendar.example/e"}

        with patch("app.api.routes.schedule.create_event", flaky_create):
            resp = _post(auth_client)

        assert resp.status_code == 200
        assert len(resp.json()["events"]) == 3, "one failure should cost exactly one task"
        assert db.query(TaskRecord).count() == 3

    def test_an_unusable_roadmap_returns_502_not_500(self, auth_client, connected_user, calendar):
        with patch("app.api.routes.schedule.get_llm", lambda: FakeLLM(json_result={"milestones": []})):
            resp = _post(auth_client)

        assert resp.status_code == 400
        assert "No tasks generated" in resp.json()["detail"]

    def test_no_free_slots_reports_rather_than_failing(
        self, auth_client, connected_user, calendar
    ):
        with patch("app.api.routes.schedule.build_free_slots", lambda **kw: []):
            resp = _post(auth_client)

        assert resp.status_code == 200
        assert resp.json()["events"] == []
        assert "No available slots" in resp.json()["message"]

    def test_unschedulable_tasks_are_reported_in_the_message(
        self, auth_client, connected_user, calendar
    ):
        # Half an hour a day cannot fit a 300-minute task anywhere.
        resp = _post(auth_client, horizon_days=2, daily_hours=0.5)
        body = resp.json()
        assert resp.status_code == 200
        assert "did not fit" in body["message"]

    def test_events_carry_calendar_metadata(self, auth_client, connected_user, calendar):
        event = _post(auth_client).json()["events"][0]
        assert event["id"].startswith("evt-")
        assert event["htmlLink"].startswith("https://")
        assert event["start"] < event["end"]

    def test_calendar_summaries_are_prefixed(self, auth_client, connected_user, calendar):
        _post(auth_client)
        assert all(c["summary"].startswith("🧠 Task:") for c in calendar["created"])
