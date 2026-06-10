"""run_workflow_default_mode stashes exactly ONE live observation.

Success -> the FINAL step's observation, marked executed_steps (end-state, not
step 1). Failure -> the FAILING step's observation, marked failed_step_index /
failed_step_name. Never a per-step array. Driven with fakes (no browser).
"""

from types import SimpleNamespace

import cli.modes.workflow as wf
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


class _FakeHistory:
    def __init__(self, *a, **k): pass
    def add_step(self, *a, **k): pass
    def get_current_file_content(self): return []


def _step(name):
    return SimpleNamespace(enabled=True, action="click", locator_type="text",
                           locator_value=name, extra_value="", name=f"click:{name}")


def _workflow(steps):
    return SimpleNamespace(name="login", platform="web", steps=steps, vars={})


def _args():
    return SimpleNamespace(platform="web", env="dev", workflow="wf.yaml",
                           workflow_var=[], vision=False, playground_sink=False)


def _wire(monkeypatch, *, succeed_through):
    """succeed_through: number of leading steps that succeed (rest fail)."""
    monkeypatch.setattr(wf, "_build_reporter", lambda *a, **k: _FakeReporter())
    monkeypatch.setattr(wf, "_emit_run_started", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_apply_resume_summary", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(wf, "get_initial_header", lambda label=None: [])
    monkeypatch.setattr(wf, "save_to_disk", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_ensure_history_manager", lambda: None)
    monkeypatch.setattr(wf, "_ensure_executor_runtime", lambda: None)
    monkeypatch.setattr(wf, "_ensure_ui_compressors", lambda: None)
    monkeypatch.setattr(wf, "current_url", lambda adapter, platform: "https://x/done")
    monkeypatch.setattr(wf, "build_sink_from_args", lambda *a, **k: None)
    monkeypatch.setattr(wf, "maybe_push_step", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_capture_ui_state",
                        lambda args, adapter, reporter, step: ('{"ui_elements":[{"ref":"@1"}]}', None))
    monkeypatch.setattr(wf._shared, "StepHistoryManager", _FakeHistory)

    class _Exec:
        def __init__(self): self.n = 0
        def execute_and_record(self, action_data):
            self.n += 1
            if self.n <= succeed_through:
                return {"success": True, "code_lines": ["x\n"], "action_description": "click"}
            return {"success": False, "error_code": "E037", "action_description": "click"}

    monkeypatch.setattr(wf._shared, "UIExecutor", lambda device, platform: _Exec())


def test_workflow_success_stashes_final_step_only(monkeypatch):
    mgr = _SharedAdapterManager()
    _wire(monkeypatch, succeed_through=3)
    wfdef = _workflow([_step("a"), _step("b"), _step("c")])
    monkeypatch.setattr(wf, "_load_workflow_definition", lambda args: wfdef)

    rc = wf.run_workflow_default_mode(_args(), "out.py", {}, shared_adapter_manager=mgr)
    assert rc == 0
    obs = mgr.take_last_observation()
    assert obs is not None
    assert obs["ok"] is True
    assert obs["executed_steps"] == 3          # end-state marker, ONE observation
    assert obs["action"] == "click:c"          # the FINAL step
    assert "ui_tree" in obs


def test_workflow_failure_stashes_failing_step(monkeypatch):
    mgr = _SharedAdapterManager()
    _wire(monkeypatch, succeed_through=1)       # step 2 fails
    wfdef = _workflow([_step("a"), _step("b"), _step("c")])
    monkeypatch.setattr(wf, "_load_workflow_definition", lambda args: wfdef)

    rc = wf.run_workflow_default_mode(_args(), "out.py", {}, shared_adapter_manager=mgr)
    assert rc == 1
    obs = mgr.take_last_observation()
    assert obs is not None
    assert obs["ok"] is False
    assert obs["failed_step_index"] == 2
    assert obs["failed_step_name"] == "click:b"
    assert obs["error_code"] == "E037"


def test_workflow_without_manager_does_not_crash(monkeypatch):
    _wire(monkeypatch, succeed_through=3)
    wfdef = _workflow([_step("a")])
    monkeypatch.setattr(wf, "_load_workflow_definition", lambda args: wfdef)
    rc = wf.run_workflow_default_mode(_args(), "out.py", {})
    assert rc == 0
