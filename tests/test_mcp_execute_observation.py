"""MCP ui_agent_execute folds the live post-action observation into its response.

Proves component 4 without a browser: monkeypatch _dispatch_execution to stash a
known observation on the manager (as the real execute mode does), then assert
build_tool_response_payload surfaces its agent-facing fields — at parity with
shell --action --json.
"""

import cli.dispatch as dispatch
import cli.tool_protocol_handlers as tph
from common.tool_protocol import ActionToolControl, ToolRequest
from cli.shared import _SharedAdapterManager


def _patch_handler_io(monkeypatch):
    # Skip the file-backed bits unrelated to the fold.
    monkeypatch.setattr(tph, "_find_case_memory_hit", lambda *a, **k: None)
    monkeypatch.setattr(tph, "_load_context_content", lambda args: ("", {}))
    monkeypatch.setattr(tph, "_resolve_new_run_dir", lambda *a, **k: None)


def _execute_request():
    return ToolRequest(
        operation="execute",
        platform="web",
        action=ActionToolControl(action="click", locator_type="text", locator_value="Login"),
    )


def test_folds_success_observation(monkeypatch):
    mgr = _SharedAdapterManager()
    _patch_handler_io(monkeypatch)

    def fake_dispatch(args, mode, out, ctx, resume, shared_adapter_manager=None):
        shared_adapter_manager.set_last_observation({
            "ok": True, "action": "click:Login", "platform": "web",
            "ui_tree": {"ui_elements": [{"ref": "@1", "text": "Home"}]},
            "element_count": 1, "current_url": "https://x/home",
            "output_script": "t.py",
        })
        return 0

    monkeypatch.setattr(dispatch, "_dispatch_execution", fake_dispatch)
    resp = tph.build_tool_response_payload(_execute_request(), shared_adapter_manager=mgr)

    assert resp["ok"] is True
    assert resp["element_count"] == 1
    assert resp["ui_tree"]["ui_elements"][0]["text"] == "Home"
    assert resp["current_url"] == "https://x/home"
    assert mgr.take_last_observation() is None  # handler consumed it


def test_folds_failure_observation_makes_diagnosis_real(monkeypatch):
    mgr = _SharedAdapterManager()
    _patch_handler_io(monkeypatch)

    def fake_dispatch(args, mode, out, ctx, resume, shared_adapter_manager=None):
        shared_adapter_manager.set_last_observation({
            "ok": False, "action": "click:Login", "platform": "web",
            "result": "engine_error", "assertion_failed": False,
            "error_code": "E037", "message": "Element could not be located.",
            "fix": "Re-inspect, scroll the target into view, or add --vision.",
            "candidates": [{"text": "Log in", "score": 0.83,
                            "locator": {"type": "ref", "value": "@1"}}],
            "recommended_next_step": {"action": "retry_with_candidate",
                                      "hint": "Try @1 ('Log in')",
                                      "locator": {"type": "ref", "value": "@1"}},
            "ui_tree": {"ui_elements": [{"ref": "@1", "text": "Log in"}]},
            "element_count": 1, "current_url": "https://x/login",
        })
        return 1

    monkeypatch.setattr(dispatch, "_dispatch_execution", fake_dispatch)
    resp = tph.build_tool_response_payload(_execute_request(), shared_adapter_manager=mgr)

    assert resp["ok"] is False
    assert resp["candidates"][0]["text"] == "Log in"
    assert resp["recommended_next_step"]["action"] == "retry_with_candidate"
    # failure_diagnosis is now REAL (from the live observation, not summary.json).
    assert resp["failure_diagnosis"]["error_code"] == "E037"
    assert "Re-inspect" in resp["failure_diagnosis"]["fix"]


def test_workflow_markers_are_projected(monkeypatch):
    # The single-observation markers (executed_steps on success; failed_step_*
    # on failure) must surface when present.
    mgr = _SharedAdapterManager()
    _patch_handler_io(monkeypatch)

    def fake_dispatch(args, mode, out, ctx, resume, shared_adapter_manager=None):
        shared_adapter_manager.set_last_observation({
            "ok": True, "action": "assert_exist:Dashboard", "platform": "web",
            "ui_tree": {"ui_elements": []}, "element_count": 0,
            "current_url": "https://x/done", "output_script": "t.py",
            "executed_steps": 3,
        })
        return 0

    monkeypatch.setattr(dispatch, "_dispatch_execution", fake_dispatch)
    resp = tph.build_tool_response_payload(_execute_request(), shared_adapter_manager=mgr)
    assert resp["executed_steps"] == 3


def test_no_manager_yields_no_observation_fields(monkeypatch):
    _patch_handler_io(monkeypatch)

    def fake_dispatch(args, mode, out, ctx, resume, shared_adapter_manager=None):
        return 0

    monkeypatch.setattr(dispatch, "_dispatch_execution", fake_dispatch)
    resp = tph.build_tool_response_payload(_execute_request(), shared_adapter_manager=None)
    assert "ui_tree" not in resp
    assert resp["ok"] is True
