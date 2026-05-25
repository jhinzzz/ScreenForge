"""Tests for common/ai_autonomous.py — AutonomousBrain plan and decision."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_config(monkeypatch):
    monkeypatch.setattr("config.config.OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("config.config.OPENAI_BASE_URL", "http://localhost")
    monkeypatch.setattr("config.config.VISION_API_KEY", "test-key")
    monkeypatch.setattr("config.config.VISION_BASE_URL", "http://localhost")
    monkeypatch.setattr("config.config.VISION_MODEL_NAME", "gpt-4o")
    monkeypatch.setattr("config.config.MODEL_NAME", "gpt-4o")
    monkeypatch.setattr("config.config.CACHE_DIR", "/tmp/test_cache")
    monkeypatch.setattr("config.config.CACHE_ENABLED", False)
    monkeypatch.setattr("config.config.CACHE_TTL_DAYS", 1)
    monkeypatch.setattr("config.config.CACHE_MAX_SIZE_MB", 10)


@pytest.fixture
def autonomous_brain(mock_config):
    with patch("common.ai.OpenAI") as mock_openai_cls:
        mock_openai_cls.return_value = MagicMock()
        from common.ai_autonomous import AutonomousBrain
        return AutonomousBrain()


def _make_response(content: str):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


class TestGetExecutionPlan:
    def test_returns_plan_payload(self, autonomous_brain):
        plan = {
            "current_state_summary": "On login page",
            "planned_steps": [{"action": "click", "target": "#login"}],
            "suggested_assertion": "assert logged in",
            "risks": [],
        }
        autonomous_brain.text_client.chat.completions.create.return_value = _make_response(json.dumps(plan))

        result = autonomous_brain.get_execution_plan(
            goal="test login",
            context="",
            ui_json='{"ui_elements": []}',
            history=[],
            platform="web",
        )
        assert result["current_state_summary"] == "On login page"
        assert len(result["planned_steps"]) == 1

    def test_handles_markdown_wrapped_response(self, autonomous_brain):
        plan = {
            "current_state_summary": "Dashboard",
            "planned_steps": [],
            "suggested_assertion": "",
            "risks": [],
        }
        content = f"```json\n{json.dumps(plan)}\n```"
        autonomous_brain.text_client.chat.completions.create.return_value = _make_response(content)

        result = autonomous_brain.get_execution_plan(
            goal="check dashboard", context="", ui_json="{}", history=[], platform="web"
        )
        assert result["current_state_summary"] == "Dashboard"

    def test_returns_fallback_on_error(self, autonomous_brain):
        autonomous_brain.text_client.chat.completions.create.side_effect = Exception("timeout")

        result = autonomous_brain.get_execution_plan(
            goal="test", context="", ui_json="{}", history=[], platform="web"
        )
        assert result["planned_steps"] == []
        assert "risks" in result

    def test_no_client_returns_error(self, autonomous_brain):
        autonomous_brain.text_client = None
        autonomous_brain.vision_client = None

        result = autonomous_brain.get_execution_plan(
            goal="test", context="", ui_json="{}", history=[], platform="web"
        )
        assert result["planned_steps"] == []


class TestGetNextAutonomousAction:
    def test_returns_action_decision(self, autonomous_brain):
        decision = {
            "status": "continue",
            "thought": "Need to click login button",
            "result": {"action": "click", "locator_type": "text", "locator_value": "Login"},
        }
        autonomous_brain.text_client.chat.completions.create.return_value = _make_response(json.dumps(decision))

        result = autonomous_brain.get_next_autonomous_action(
            goal="test login",
            context="",
            ui_json='{"ui_elements": []}',
            history=[],
            platform="web",
        )
        assert result["status"] == "continue"
        assert result["result"]["action"] == "click"

    def test_handles_completed_status(self, autonomous_brain):
        decision = {
            "status": "completed",
            "thought": "All steps done",
            "result": {},
        }
        autonomous_brain.text_client.chat.completions.create.return_value = _make_response(json.dumps(decision))

        result = autonomous_brain.get_next_autonomous_action(
            goal="test", context="", ui_json="{}", history=[], platform="web"
        )
        assert result["status"] == "completed"

    def test_returns_failed_on_api_error(self, autonomous_brain):
        autonomous_brain.text_client.chat.completions.create.side_effect = Exception("rate limit")

        result = autonomous_brain.get_next_autonomous_action(
            goal="test", context="", ui_json="{}", history=[], platform="web"
        )
        assert result["status"] == "failed"

    def test_no_client_returns_failed(self, autonomous_brain):
        autonomous_brain.text_client = None
        autonomous_brain.vision_client = None

        result = autonomous_brain.get_next_autonomous_action(
            goal="test", context="", ui_json="{}", history=[], platform="web"
        )
        assert result["status"] == "failed"
