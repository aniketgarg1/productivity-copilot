"""Roadmap normalisation — the model's output is not trusted."""

import pytest

from app.agents.planner import (
    MAX_TASK_MINUTES,
    MIN_TASK_MINUTES,
    ROADMAP_SCHEMA,
    make_roadmap,
    normalize_roadmap,
)
from app.schemas.roadmap import Roadmap
from tests.conftest import FakeLLM, roadmap_fixture


class TestSchemaCompatibility:
    def test_schema_avoids_keywords_structured_outputs_rejects(self):
        """minimum/maximum/minItems 400 on the gpt-4.1-mini default."""
        banned = {"minimum", "maximum", "minItems", "maxItems", "multipleOf", "pattern"}

        def walk(node, path="root"):
            if isinstance(node, dict):
                for key, value in node.items():
                    assert key not in banned, f"{path}.{key} is rejected by structured outputs"
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    walk(item, f"{path}[{i}]")

        walk(ROADMAP_SCHEMA)

    def test_every_object_requires_all_its_properties(self):
        """strict mode demands `required` list every property."""

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object" and "properties" in node:
                    assert set(node["properties"]) == set(node.get("required", []))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(ROADMAP_SCHEMA)


class TestNormalizeRoadmap:
    def test_a_good_roadmap_passes_through_intact(self):
        out = normalize_roadmap(roadmap_fixture(), "Learn Rust", 14)
        Roadmap.model_validate(out)
        assert len(out["milestones"]) == 2
        assert out["goal"] == "Learn Rust"

    def test_estimates_are_clamped(self):
        raw = {"milestones": [{"title": "M", "tasks": [
            {"title": "huge", "estimate_minutes": 99999},
            {"title": "tiny", "estimate_minutes": 1},
            {"title": "negative", "estimate_minutes": -30},
        ]}]}
        tasks = normalize_roadmap(raw, "g", 30)["milestones"][0]["tasks"]
        assert [t["estimate_minutes"] for t in tasks] == [
            MAX_TASK_MINUTES, MIN_TASK_MINUTES, MIN_TASK_MINUTES
        ]

    def test_untitled_tasks_are_dropped(self):
        raw = {"milestones": [{"title": "M", "tasks": [
            {"title": "keep", "estimate_minutes": 30},
            {"title": "   ", "estimate_minutes": 30},
            {"estimate_minutes": 30},
        ]}]}
        tasks = normalize_roadmap(raw, "g", 30)["milestones"][0]["tasks"]
        assert [t["title"] for t in tasks] == ["keep"]

    def test_milestones_with_no_usable_tasks_are_dropped(self):
        raw = {"milestones": [
            {"title": "empty", "tasks": []},
            {"title": "real", "tasks": [{"title": "t", "estimate_minutes": 30}]},
        ]}
        out = normalize_roadmap(raw, "g", 30)
        assert [m["title"] for m in out["milestones"]] == ["real"]

    def test_an_invalid_difficulty_falls_back(self):
        raw = {"milestones": [{"title": "M", "tasks": [
            {"title": "t", "estimate_minutes": 30, "difficulty": "impossible"},
        ]}]}
        assert normalize_roadmap(raw, "g", 30)["milestones"][0]["tasks"][0]["difficulty"] == "medium"

    def test_malformed_resources_are_filtered(self):
        raw = {"milestones": [{"title": "M", "tasks": [{
            "title": "t", "estimate_minutes": 30,
            "resources": [
                {"title": "ok", "url": "https://example.com", "type": "docs"},
                {"title": "no url"},
                "not a dict",
            ],
        }]}]}
        resources = normalize_roadmap(raw, "g", 30)["milestones"][0]["tasks"][0]["resources"]
        assert len(resources) == 1
        assert resources[0]["url"] == "https://example.com"

    def test_missing_goal_falls_back_to_the_users_text(self):
        out = normalize_roadmap({"milestones": []}, "My actual goal", 30)
        assert out["goal"] == "My actual goal"

    @pytest.mark.parametrize("bad", [None, {}, {"milestones": None}, {"milestones": ["junk"]}])
    def test_garbage_input_does_not_raise(self, bad):
        out = normalize_roadmap(bad, "g", 30)
        assert out["milestones"] == []
        assert out["goal"] == "g"

    def test_output_always_satisfies_the_response_model(self):
        raw = {"milestones": [{"title": "M", "tasks": [{"title": "t"}]}]}
        Roadmap.model_validate(normalize_roadmap(raw, "g", 30))


class TestMakeRoadmap:
    async def test_model_output_is_normalised_before_returning(self):
        llm = FakeLLM(json_result={"milestones": [{"title": "M", "tasks": [
            {"title": "t", "estimate_minutes": 9999},
        ]}]})
        out = await make_roadmap(llm, "Learn Rust", 14)

        assert out["goal"] == "Learn Rust"
        assert out["milestones"][0]["tasks"][0]["estimate_minutes"] == MAX_TASK_MINUTES
        Roadmap.model_validate(out)

    async def test_the_horizon_reaches_the_prompt(self):
        llm = FakeLLM(json_result=roadmap_fixture())
        await make_roadmap(llm, "Learn Rust", 21)

        kind, kwargs = llm.calls[0]
        assert kind == "json"
        assert "21" in kwargs["user"]
        assert "Learn Rust" in kwargs["user"]
