"""Tests for common/ai.py — AIBrain action decision and cache interaction."""

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
def brain(mock_config):
    with patch("common.ai.OpenAI") as mock_openai_cls:
        mock_openai_cls.side_effect = [MagicMock(), MagicMock()]
        from common.ai import AIBrain
        return AIBrain()


class TestVerifyLocatorInUi:
    def test_no_locator_type_passes(self, brain):
        decision = {"action": "swipe", "locator_type": "", "locator_value": ""}
        assert brain._verify_locator_in_ui(decision, {"ui_elements": []}) is True

    def test_text_locator_found(self, brain):
        decision = {"locator_type": "text", "locator_value": "Login"}
        ui = {"ui_elements": [{"text": "Login", "id": ""}]}
        assert brain._verify_locator_in_ui(decision, ui) is True

    def test_text_locator_not_found(self, brain):
        decision = {"locator_type": "text", "locator_value": "Login"}
        ui = {"ui_elements": [{"text": "Register", "id": ""}]}
        assert brain._verify_locator_in_ui(decision, ui) is False

    def test_id_locator_found(self, brain):
        decision = {"locator_type": "resourceId", "locator_value": "btn_submit"}
        ui = {"ui_elements": [{"text": "", "id": "btn_submit"}]}
        assert brain._verify_locator_in_ui(decision, ui) is True

    def test_description_locator_found(self, brain):
        decision = {"locator_type": "description", "locator_value": "Close dialog"}
        ui = {"ui_elements": [{"desc": "Close dialog", "text": ""}]}
        assert brain._verify_locator_in_ui(decision, ui) is True

    def test_css_locator_passthrough(self, brain):
        decision = {"locator_type": "css", "locator_value": "#btn"}
        ui = {"ui_elements": []}
        assert brain._verify_locator_in_ui(decision, ui) is True


class TestGetAction:
    def _make_llm_response(self, content: str):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = content
        return response

    def test_returns_parsed_result(self, brain):
        result_json = json.dumps({"result": {"action": "click", "locator_type": "text", "locator_value": "Login"}})
        brain.text_client.chat.completions.create.return_value = self._make_llm_response(result_json)

        result = brain.get_action("click login button", '{"ui_elements": []}', "web", skip_cache=True)
        assert result["action"] == "click"
        assert result["locator_value"] == "Login"

    def test_handles_markdown_wrapped_json(self, brain):
        content = '```json\n{"result": {"action": "input", "locator_type": "css", "locator_value": "#email"}}\n```'
        brain.text_client.chat.completions.create.return_value = self._make_llm_response(content)

        result = brain.get_action("type in email", '{"ui_elements": []}', "web", skip_cache=True)
        assert result["action"] == "input"

    def test_returns_empty_on_parse_failure(self, brain):
        brain.text_client.chat.completions.create.return_value = self._make_llm_response("not json at all")

        result = brain.get_action("do something", '{"ui_elements": []}', "web", skip_cache=True)
        assert result == {}

    def test_returns_empty_on_api_error(self, brain):
        brain.text_client.chat.completions.create.side_effect = Exception("connection timeout")

        result = brain.get_action("do something", '{"ui_elements": []}', "web", skip_cache=True)
        assert result == {}

    def test_uses_vision_client_when_screenshot_provided(self, brain):
        result_json = json.dumps({"result": {"action": "click", "locator_type": "text", "locator_value": "OK"}})
        brain.vision_client.chat.completions.create.return_value = self._make_llm_response(result_json)

        result = brain.get_action(
            "click ok", '{"ui_elements": []}', "web",
            screenshot_base64="base64data", skip_cache=True,
        )
        assert result["action"] == "click"
        brain.vision_client.chat.completions.create.assert_called_once()
        brain.text_client.chat.completions.create.assert_not_called()
