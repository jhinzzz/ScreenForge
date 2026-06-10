"""Each execution mode threads the executor's error_code into reporter.finalize().

This is what makes summary.json carry a real error_code, so the MCP handler can
build a real failure_diagnosis on the --goal path (which produces no live
observation to fold). Driven with fakes (no browser / no model), mirroring the
fake-adapter pattern in tests/test_action_mode_observation_stash.py.

The contract: a failing executor result whose error_code is "E0xx" must reach
finalize(error_code="E0xx"); a clean success finalizes with error_code="".
"""

from types import SimpleNamespace

import cli.modes.action as action
import cli.modes.default as default
import cli.modes.workflow as wf


class _SpyReporter:
    """Captures the kwargs of the single finalize() call."""

    def __init__(self):
        self.finalize_kwargs = None

    def emit_event(self, *a, **k):
        pass

    def update_control_summary(self, *a, **k):
        pass

    def update_summary(self, *a, **k):
        pass

    def save_screenshot(self, *a, **k):
        return ""

    def finalize(self, **k):
        self.finalize_kwargs = k


class _FakeAdapter:
    def __init__(self):
        self.driver = object()

    def teardown(self):
        pass


class _FakeHistory:
    def __init__(self, *a, **k):
        pass

    def add_step(self, *a, **k):
        pass

    def get_history(self):
        return []

    def get_current_file_content(self):
        return []


# ---- action mode ---------------------------------------------------------


def _action_args():
    return SimpleNamespace(
        platform="web", env="dev", json=False, vision=False,
        action="click", action_name="", locator_type="text",
        locator_value="Login", extra_value="", playground_sink=False,
    )


def _wire_action(monkeypatch, reporter, *, success, error_code=""):
    monkeypatch.setattr(action, "_build_reporter", lambda *a, **k: reporter)
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
    monkeypatch.setattr(action, "current_url", lambda adapter, platform: "https://x")
    monkeypatch.setattr(action, "build_sink_from_args", lambda *a, **k: None)
    monkeypatch.setattr(action, "maybe_push_step", lambda *a, **k: None)
    monkeypatch.setattr(action, "_capture_ui_state",
                        lambda *a, **k: ('{"ui_elements":[]}', None))
    monkeypatch.setattr(action, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(action._shared, "StepHistoryManager", _FakeHistory)

    class _Exec:
        def execute_and_record(self, action_data):
            if success:
                return {"success": True, "code_lines": ["x\n"], "action_description": "click"}
            return {"success": False, "error_code": error_code, "action_description": "click"}

    monkeypatch.setattr(action._shared, "UIExecutor", lambda device, platform: _Exec())


def test_action_failure_threads_error_code(monkeypatch, tmp_path):
    rep = _SpyReporter()
    _wire_action(monkeypatch, rep, success=False, error_code="E037")
    rc = action.run_action_default_mode(_action_args(), str(tmp_path / "o.py"), {})
    assert rc == 1
    assert rep.finalize_kwargs["error_code"] == "E037"


def test_action_success_threads_empty_error_code(monkeypatch, tmp_path):
    rep = _SpyReporter()
    _wire_action(monkeypatch, rep, success=True)
    rc = action.run_action_default_mode(_action_args(), str(tmp_path / "o.py"), {})
    assert rc == 0
    assert rep.finalize_kwargs["error_code"] == ""


# ---- workflow mode -------------------------------------------------------


def _wf_step(name):
    return SimpleNamespace(enabled=True, action="click", locator_type="text",
                           locator_value=name, extra_value="", name=f"click:{name}")


def _wf_args():
    return SimpleNamespace(platform="web", env="dev", workflow="wf.yaml",
                           workflow_var=[], vision=False, playground_sink=False)


def _wire_wf(monkeypatch, reporter, *, succeed_through, error_code=""):
    monkeypatch.setattr(wf, "_build_reporter", lambda *a, **k: reporter)
    monkeypatch.setattr(wf, "_emit_run_started", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_apply_resume_summary", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(wf, "get_initial_header", lambda label=None: [])
    monkeypatch.setattr(wf, "save_to_disk", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_ensure_history_manager", lambda: None)
    monkeypatch.setattr(wf, "_ensure_executor_runtime", lambda: None)
    monkeypatch.setattr(wf, "_ensure_ui_compressors", lambda: None)
    monkeypatch.setattr(wf, "current_url", lambda adapter, platform: "https://x")
    monkeypatch.setattr(wf, "build_sink_from_args", lambda *a, **k: None)
    monkeypatch.setattr(wf, "maybe_push_step", lambda *a, **k: None)
    monkeypatch.setattr(wf, "_capture_ui_state", lambda *a, **k: ('{"ui_elements":[]}', None))
    monkeypatch.setattr(wf._shared, "StepHistoryManager", _FakeHistory)

    class _Exec:
        def __init__(self):
            self.n = 0

        def execute_and_record(self, action_data):
            self.n += 1
            if self.n <= succeed_through:
                return {"success": True, "code_lines": ["x\n"], "action_description": "click"}
            return {"success": False, "error_code": error_code, "action_description": "click"}

    monkeypatch.setattr(wf._shared, "UIExecutor", lambda device, platform: _Exec())


def test_workflow_failure_threads_error_code(monkeypatch):
    rep = _SpyReporter()
    _wire_wf(monkeypatch, rep, succeed_through=1, error_code="E038")
    monkeypatch.setattr(wf, "_load_workflow_definition",
                        lambda args: SimpleNamespace(name="w", platform="web",
                                                     steps=[_wf_step("a"), _wf_step("b")], vars={}))
    rc = wf.run_workflow_default_mode(_wf_args(), "o.py", {})
    assert rc == 1
    assert rep.finalize_kwargs["error_code"] == "E038"


def test_workflow_success_threads_empty_error_code(monkeypatch):
    rep = _SpyReporter()
    _wire_wf(monkeypatch, rep, succeed_through=2)
    monkeypatch.setattr(wf, "_load_workflow_definition",
                        lambda args: SimpleNamespace(name="w", platform="web",
                                                     steps=[_wf_step("a"), _wf_step("b")], vars={}))
    rc = wf.run_workflow_default_mode(_wf_args(), "o.py", {})
    assert rc == 0
    assert rep.finalize_kwargs["error_code"] == ""


# ---- default (--goal autonomous) mode ------------------------------------


class _FakeBrain:
    """Returns a 'running' decision with a concrete action every step."""

    def get_next_autonomous_action(self, **k):
        return {"status": "running",
                "result": {"action": "click", "locator_type": "text", "locator_value": "X"}}


def _default_args():
    return SimpleNamespace(platform="web", env="dev", goal="do it", vision=False,
                           max_steps=5, max_retries=1)


def _wire_default(monkeypatch, reporter, *, error_code):
    monkeypatch.setattr(default, "_build_reporter", lambda *a, **k: reporter)
    monkeypatch.setattr(default, "_emit_run_started", lambda *a, **k: None)
    monkeypatch.setattr(default, "_apply_resume_summary", lambda *a, **k: None)
    monkeypatch.setattr(default, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(default, "get_initial_header", lambda label=None: [])
    monkeypatch.setattr(default, "save_to_disk", lambda *a, **k: None)
    monkeypatch.setattr(default, "_ensure_history_manager", lambda: None)
    monkeypatch.setattr(default, "_ensure_executor_runtime", lambda: None)
    monkeypatch.setattr(default, "_ensure_runtime_classes", lambda: None)
    monkeypatch.setattr(default, "_capture_ui_state",
                        lambda *a, **k: ('{"ui_elements":[]}', ""))
    monkeypatch.setattr(default._shared, "StepHistoryManager", _FakeHistory)
    monkeypatch.setattr(default._shared, "AutonomousBrain", _FakeBrain)

    class _Exec:
        def execute_and_record(self, action_data):
            return {"success": False, "error_code": error_code, "action_description": "click"}

    monkeypatch.setattr(default._shared, "UIExecutor", lambda device, platform: _Exec())


def test_default_goal_failure_threads_error_code(monkeypatch):
    # The --goal loop: action fails, circuit breaker trips at max_retries=1, and
    # the executor's error_code must reach finalize so summary.json carries it.
    rep = _SpyReporter()
    _wire_default(monkeypatch, rep, error_code="E037")
    rc = default.run_default_mode(_default_args(), "o.py", "", {})
    assert rc == 1
    assert rep.finalize_kwargs["error_code"] == "E037"
