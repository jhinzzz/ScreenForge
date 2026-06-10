"""run_action_default_mode stashes ONE live observation when a manager is present.

Drives the real mode function with fakes (no browser), mirroring the
fake-adapter/monkeypatch pattern in tests/test_mcp_ref_cache.py. Proves the mode
wires set_last_observation on success, and that the exit code is unchanged.
"""

from types import SimpleNamespace

import cli.modes.action as action
from cli.shared import _SharedAdapterManager


class _FakeReporter:
    def emit_event(self, *a, **k): pass
    def update_control_summary(self, *a, **k): pass
    def update_summary(self, *a, **k): pass
    def finalize(self, *a, **k): pass
    def save_screenshot(self, *a, **k): return ""


class _FakeAdapter:
    def __init__(self): self.driver = object()
    def teardown(self): pass


class _FakeExecutor:
    def execute_and_record(self, action_data):
        return {"success": True, "code_lines": ["page.click()\n"], "action_description": "click"}


class _FakeHistory:
    def __init__(self, *a, **k): pass
    def add_step(self, *a, **k): pass
    def get_current_file_content(self): return []


def _args():
    return SimpleNamespace(
        platform="web", env="dev", json=False, vision=False,
        action="click", action_name="", locator_type="text",
        locator_value="Login", extra_value="", playground_sink=False,
    )


def _wire(monkeypatch, mgr):
    monkeypatch.setattr(action, "_build_reporter", lambda *a, **k: _FakeReporter())
    monkeypatch.setattr(action, "_emit_run_started", lambda *a, **k: None)
    monkeypatch.setattr(action, "_apply_resume_summary", lambda *a, **k: None)
    monkeypatch.setattr(action, "_build_inline_action_data",
                        lambda args: {"name": "click:Login", "action": "click",
                                      "locator_type": "text", "locator_value": "Login",
                                      "extra_value": ""})
    monkeypatch.setattr(action, "_build_action_summary",
                        lambda args, data, executed_steps=0: {
                            "action_name": "click:Login", "action": "click",
                            "locator_type": "text", "locator_value": "Login",
                            "extra_value": ""})
    monkeypatch.setattr(action, "get_initial_header", lambda label=None: [])
    monkeypatch.setattr(action, "save_to_disk", lambda *a, **k: None)
    monkeypatch.setattr(action, "_ensure_history_manager", lambda: None)
    monkeypatch.setattr(action, "_ensure_executor_runtime", lambda: None)
    monkeypatch.setattr(action, "_ensure_ui_compressors", lambda: None)
    monkeypatch.setattr(action, "current_url", lambda adapter, platform: "https://x/home")
    monkeypatch.setattr(action, "build_sink_from_args", lambda *a, **k: None)
    monkeypatch.setattr(action, "maybe_push_step", lambda *a, **k: None)
    monkeypatch.setattr(action, "_capture_ui_state",
                        lambda args, adapter, reporter, step: ('{"ui_elements":[{"ref":"@1","text":"Home"}]}', None))
    monkeypatch.setattr(action._shared, "StepHistoryManager", _FakeHistory)
    # Manager yields fakes; no real browser.
    monkeypatch.setattr(mgr, "get_or_create", lambda platform, env="dev": _FakeAdapter())
    monkeypatch.setattr(mgr, "get_executor", lambda platform, env="dev": _FakeExecutor())


def test_success_stashes_observation(monkeypatch, tmp_path):
    mgr = _SharedAdapterManager()
    _wire(monkeypatch, mgr)
    out = str(tmp_path / "out.py")  # does not exist -> new-file branch
    rc = action.run_action_default_mode(_args(), out, {}, shared_adapter_manager=mgr)
    assert rc == 0
    obs = mgr.take_last_observation()
    assert obs is not None
    assert obs["ok"] is True
    assert obs["element_count"] == 1
    assert obs["ui_tree"]["ui_elements"][0]["text"] == "Home"
    assert obs["current_url"] == "https://x/home"


def test_no_manager_does_not_stash_and_returns_zero(monkeypatch, tmp_path):
    # Shell path: no manager, no --json. Must not crash, must return 0, and there
    # is no stash to populate.
    mgr = _SharedAdapterManager()  # only used to assert it stays empty
    monkeypatch.setattr(action, "_build_reporter", lambda *a, **k: _FakeReporter())
    monkeypatch.setattr(action, "_emit_run_started", lambda *a, **k: None)
    monkeypatch.setattr(action, "_apply_resume_summary", lambda *a, **k: None)
    monkeypatch.setattr(action, "_build_inline_action_data",
                        lambda args: {"name": "click:Login", "action": "click",
                                      "locator_type": "text", "locator_value": "Login",
                                      "extra_value": ""})
    monkeypatch.setattr(action, "_build_action_summary",
                        lambda args, data, executed_steps=0: {
                            "action_name": "click:Login", "action": "click",
                            "locator_type": "text", "locator_value": "Login",
                            "extra_value": ""})
    monkeypatch.setattr(action, "get_initial_header", lambda label=None: [])
    monkeypatch.setattr(action, "save_to_disk", lambda *a, **k: None)
    monkeypatch.setattr(action, "_ensure_history_manager", lambda: None)
    monkeypatch.setattr(action, "_ensure_executor_runtime", lambda: None)
    monkeypatch.setattr(action, "build_sink_from_args", lambda *a, **k: None)
    monkeypatch.setattr(action, "maybe_push_step", lambda *a, **k: None)
    monkeypatch.setattr(action, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(action._shared, "StepHistoryManager", _FakeHistory)
    monkeypatch.setattr(action._shared, "UIExecutor", lambda device, platform: _FakeExecutor())
    out = str(tmp_path / "out.py")
    rc = action.run_action_default_mode(_args(), out, {})
    assert rc == 0
    assert mgr.take_last_observation() is None
