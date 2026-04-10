# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

import agent_cli
from common.run_reporter import RunReporter
from common.tool_protocol import ToolRequest


class _FakeAdapter:
    def __init__(self):
        self.driver = object()
        self.teardown_called = False

    def teardown(self):
        self.teardown_called = True


def test_tool_execute_should_reject_goal_for_agent_surfaces():
    with pytest.raises(Exception) as excinfo:
        ToolRequest.model_validate(
            {
                "operation": "execute",
                "goal": "验证登录流程",
            }
        )

    assert "goal" in str(excinfo.value)


def test_build_inspect_ui_payload_should_return_clean_ui_tree(monkeypatch):
    adapter = _FakeAdapter()

    monkeypatch.setattr(agent_cli, "_connect_adapter", lambda args, reporter: adapter)
    monkeypatch.setattr(
        agent_cli,
        "_capture_ui_state",
        lambda args, current_adapter, reporter, step_index: (
            '{"ui_elements":[{"text":"登录","id":"login-btn"}]}',
            None,
        ),
    )

    request = ToolRequest.model_validate(
        {
            "operation": "inspect_ui",
            "platform": "android",
        }
    )

    payload = agent_cli.build_tool_response_payload(request)

    assert payload["ok"] is True
    assert payload["operation"] == "inspect_ui"
    assert payload["ui_tree"]["ui_elements"][0]["text"] == "登录"
    assert payload["element_count"] == 1
    assert adapter.teardown_called is True


def test_build_load_case_memory_payload_should_return_filtered_entries(monkeypatch, tmp_path):
    memory_path = tmp_path / "case_memory.json"
    monkeypatch.setattr(agent_cli.config, "CASE_MEMORY_PATH", memory_path)

    memory_doc = {
        "version": 1,
        "updated_at": "2026-04-09T18:00:00",
        "entries": [
            {
                "memory_id": "android:action:login",
                "platform": "android",
                "control_kind": "action",
                "control_label": "点击登录",
                "source_ref": "inline://action",
                "success_count": 2,
                "failure_count": 0,
                "last_status": "success",
                "last_run_id": "run_1",
                "last_used_at": "2026-04-09T18:00:00",
                "successful_actions": ["点击登录"],
                "locator_hints": [],
                "pytest_asset": {},
                "recommended_next_step": None,
            },
            {
                "memory_id": "web:workflow:search",
                "platform": "web",
                "control_kind": "workflow",
                "control_label": "搜索流程",
                "source_ref": "/tmp/search.yaml",
                "success_count": 1,
                "failure_count": 1,
                "last_status": "failed",
                "last_run_id": "run_2",
                "last_used_at": "2026-04-09T18:10:00",
                "successful_actions": ["输入关键字"],
                "locator_hints": [],
                "pytest_asset": {},
                "recommended_next_step": {"recommended_mode": "dry_run"},
            },
        ],
    }
    memory_path.write_text(json.dumps(memory_doc, ensure_ascii=False), encoding="utf-8")

    payload = agent_cli.build_load_case_memory_payload(
        platform="android",
        control_kind="action",
        query="登录",
        limit=10,
    )

    assert payload["ok"] is True
    assert payload["operation"] == "load_case_memory"
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["control_label"] == "点击登录"


def test_run_reporter_finalize_should_update_case_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_cli.config, "CASE_MEMORY_PATH", tmp_path / "case_memory.json")

    reporter = RunReporter(
        goal="点击登录",
        platform="android",
        env_name="dev",
        output_script_path=str(tmp_path / "test_case.py"),
        base_dir=str(tmp_path / "runs"),
        execution_mode="run",
        control_kind="action",
        control_label="点击登录",
        control_source_ref="inline://action",
    )
    reporter.update_control_summary(
        action="click",
        locator_type="text",
        locator_value="登录",
    )
    reporter.emit_event(
        "action_executed",
        step=1,
        success=True,
        action_description="点击登录",
    )

    reporter.finalize(
        status="success",
        exit_code=0,
        steps_executed=1,
        last_error="",
    )

    memory_path = Path(agent_cli.config.CASE_MEMORY_PATH)
    memory_doc = json.loads(memory_path.read_text(encoding="utf-8"))

    assert len(memory_doc["entries"]) == 1
    assert memory_doc["entries"][0]["control_label"] == "点击登录"
    assert memory_doc["entries"][0]["success_count"] == 1
    assert memory_doc["entries"][0]["successful_actions"] == ["点击登录"]


def test_build_tool_response_payload_should_not_require_model_for_action(monkeypatch):
    monkeypatch.setattr(agent_cli.config, "validate_config", lambda: False)
    monkeypatch.setattr(agent_cli, "_dispatch_execution", lambda *args: 0)
    monkeypatch.setattr(agent_cli, "_list_run_dirs", lambda base_dir: set())
    monkeypatch.setattr(agent_cli, "_resolve_new_run_dir", lambda before, base_dir: None)

    request = ToolRequest.model_validate(
        {
            "operation": "execute",
            "platform": "android",
            "action": {
                "action": "click",
                "action_name": "点击登录",
                "locator_type": "text",
                "locator_value": "登录",
            },
        }
    )

    payload = agent_cli.build_tool_response_payload(request)

    assert payload["operation"] == "execute"
    assert payload["exit_code"] == 0


def test_build_tool_response_payload_should_include_case_memory_hit(monkeypatch, tmp_path):
    memory_path = tmp_path / "case_memory.json"
    monkeypatch.setattr(agent_cli.config, "CASE_MEMORY_PATH", memory_path)
    monkeypatch.setattr(agent_cli.config, "validate_config", lambda: False)
    monkeypatch.setattr(agent_cli, "_dispatch_execution", lambda *args: 0)
    monkeypatch.setattr(agent_cli, "_list_run_dirs", lambda base_dir: set())
    monkeypatch.setattr(agent_cli, "_resolve_new_run_dir", lambda before, base_dir: None)
    memory_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-04-09T19:30:00",
                "entries": [
                    {
                        "memory_id": "android:action:login",
                        "platform": "android",
                        "control_kind": "action",
                        "control_label": "点击登录",
                        "source_ref": "inline://action",
                        "success_count": 1,
                        "failure_count": 0,
                        "last_status": "success",
                        "last_run_id": "run_1",
                        "last_used_at": "2026-04-09T19:30:00",
                        "successful_actions": ["点击登录"],
                        "locator_hints": [],
                        "pytest_asset": {},
                        "recommended_next_step": None,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    request = ToolRequest.model_validate(
        {
            "operation": "execute",
            "platform": "android",
            "action": {
                "action": "click",
                "action_name": "点击登录",
                "locator_type": "text",
                "locator_value": "登录",
            },
        }
    )

    payload = agent_cli.build_tool_response_payload(request)

    assert payload["case_memory_hit"] is True
    assert payload["case_memory_entry"]["control_label"] == "点击登录"
