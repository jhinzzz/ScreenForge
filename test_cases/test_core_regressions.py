# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest

import agent_cli as autonomous_cli
import conftest as project_conftest
import main as interactive_main
from common.ai import AIBrain
from common.executor import UIExecutor
from common.ai_autonomous import AutonomousBrain
from common.cache.cache_manager import CacheManager


class _FakeCompletions:
    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"thought":"ok","status":"running","result":{"action":"click","locator_type":"text","locator_value":"登录","extra_value":""}}'
                    )
                )
            ]
        )


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


class _ExplodingDevice:
    def __call__(self, **kwargs):
        raise TypeError("bad locator")


class _TrackingAdapter:
    def __init__(self, teardown_error=None):
        self.driver = object()
        self.setup_called = False
        self.teardown_called = False
        self.teardown_error = teardown_error

    def setup(self):
        self.setup_called = True

    def teardown(self):
        self.teardown_called = True
        if self.teardown_error is not None:
            raise self.teardown_error


class _FakeImage:
    def save(self, buffer, format="PNG"):
        buffer.write(b"png-bytes")


class _AndroidScreenshotDevice:
    def screenshot(self, *args, **kwargs):
        if kwargs.get("format") == "raw":
            raise RuntimeError("raw unsupported")
        return _FakeImage()


def test_cache_total_queries_should_not_double_count_on_miss(tmp_path):
    manager = CacheManager(cache_dir=str(tmp_path), enabled=True)

    result = manager.get("点击登录", {"ui_elements": []}, "android")

    stats = manager.get_stats()
    assert result is None
    assert stats["cache_misses"] == 1
    assert stats["total_queries"] == 1


def test_cosine_similarity_batch_should_match_standard_formula():
    manager = CacheManager(enabled=False)
    scores = manager._cosine_similarity_batch([1.0, 0.0], [[2.0, 0.0]])

    assert len(scores) == 1
    assert abs(scores[0][1] - 1.0) < 1e-8


def test_autonomous_brain_should_work_in_text_mode_without_client_attr():
    brain = AutonomousBrain()
    brain.text_client = _FakeClient()
    brain.vision_client = _FakeClient()

    result = brain.get_next_autonomous_action(
        goal="测试目标",
        context="",
        ui_json='{"ui_elements": []}',
        history=[],
        platform="android",
        last_error="",
        screenshot_base64=None,
    )

    assert result["status"] == "running"
    assert result["result"]["action"] == "click"


def test_execute_and_record_should_fail_when_locator_resolution_raises():
    executor = UIExecutor(_ExplodingDevice(), platform="android")

    result = executor.execute_and_record(
        {
            "action": "click",
            "locator_type": "text",
            "locator_value": "创建",
            "extra_value": "",
        }
    )

    assert result["success"] is False
    assert result["code_lines"] == []


def test_execute_and_record_should_fail_when_locator_type_missing_for_element_action():
    executor = UIExecutor(_ExplodingDevice(), platform="android")

    result = executor.execute_and_record(
        {
            "action": "click",
            "locator_type": "",
            "locator_value": "创建",
            "extra_value": "",
        }
    )

    assert result["success"] is False
    assert result["code_lines"] == []


def test_verify_locator_in_ui_should_validate_id_locator():
    brain = AIBrain()

    assert (
        brain._verify_locator_in_ui(
            {"locator_type": "id", "locator_value": "login-btn"},
            {"ui_elements": [{"id": "login-btn"}]},
        )
        is True
    )
    assert (
        brain._verify_locator_in_ui(
            {"locator_type": "id", "locator_value": "login-btn"},
            {"ui_elements": []},
        )
        is False
    )


def test_main_should_teardown_adapter_when_launch_app_fails(monkeypatch):
    adapter = _TrackingAdapter()

    monkeypatch.setattr(interactive_main, "AndroidU2Adapter", lambda: adapter)
    monkeypatch.setattr(
        interactive_main, "launch_app", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("launch failed"))
    )
    monkeypatch.setattr(
        interactive_main.sys, "argv", ["main.py", "--platform", "android"]
    )

    with pytest.raises(SystemExit):
        interactive_main.main()

    assert adapter.setup_called is True
    assert adapter.teardown_called is True


def test_agent_cli_should_teardown_adapter_when_launch_app_fails(monkeypatch):
    adapter = _TrackingAdapter()

    monkeypatch.setattr(autonomous_cli, "AndroidU2Adapter", lambda: adapter)
    monkeypatch.setattr(
        autonomous_cli, "launch_app", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("launch failed"))
    )
    monkeypatch.setattr(
        autonomous_cli.sys,
        "argv",
        ["agent_cli.py", "--goal", "测试目标", "--platform", "android"],
    )

    with pytest.raises(SystemExit):
        autonomous_cli.main()

    assert adapter.setup_called is True
    assert adapter.teardown_called is True


def test_agent_cli_should_log_cleanup_warning_when_teardown_fails(monkeypatch):
    adapter = _TrackingAdapter(teardown_error=RuntimeError("cleanup failed"))
    warnings = []

    monkeypatch.setattr(autonomous_cli, "AndroidU2Adapter", lambda: adapter)
    monkeypatch.setattr(
        autonomous_cli, "launch_app", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("launch failed"))
    )
    monkeypatch.setattr(
        autonomous_cli.sys,
        "argv",
        ["agent_cli.py", "--goal", "测试目标", "--platform", "android"],
    )
    monkeypatch.setattr(
        autonomous_cli.log, "warning", lambda message: warnings.append(message)
    )

    with pytest.raises(SystemExit):
        autonomous_cli.main()

    assert any("清理资源时发生异常" in message for message in warnings)


def test_capture_failure_screenshot_should_handle_android_image_without_raw(monkeypatch):
    attachments = []

    monkeypatch.setattr(
        project_conftest.allure,
        "attach",
        lambda content, name, attachment_type: attachments.append(
            (content, name, attachment_type)
        ),
    )

    img_bytes = project_conftest._capture_failure_screenshot(
        _AndroidScreenshotDevice(),
        "android",
        SimpleNamespace(name="case_name"),
    )

    assert img_bytes == b"png-bytes"
    assert attachments
    assert attachments[0][0] == b"png-bytes"
