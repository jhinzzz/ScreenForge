"""Integration contract: the live-mirror sink is a pure bypass observer.

#11 — with --playground-sink OFF (the default), the call sites must behave
exactly as before: maybe_push_step returns immediately, never constructing an
event, touching the adapter, or emitting HTTP. This pins "the bypass never
pollutes the main path" so a future refactor can't silently regress the exit-code
contract. The three call sites all funnel through maybe_push_step, so locking its
disabled-path behavior locks all three.
"""

import argparse
from unittest.mock import MagicMock, patch

import requests

from cli.playground_sink import build_sink_from_args, maybe_push_step


def _args(**kw):
    base = {"session_id": "", "session_end": "", "platform": "web"}
    base.update(kw)
    return argparse.Namespace(**base)


def _result():
    return {
        "success": True,
        "code_lines": ["        d.click()\n"],
        "action_description": "click",
        "error_code": "",
    }


def _action_data():
    return {"name": "click", "action": "click", "locator_type": "text", "locator_value": "x", "extra_value": ""}


class TestSinkOffIsInert:
    def test_default_args_produce_disabled_sink(self):
        """Parser default (flag absent) → sink disabled."""
        from cli.parser import build_parser

        args = build_parser().parse_args(
            ["--action", "click", "--locator-type", "text", "--locator-value", "x"]
        )
        assert args.playground_sink is False
        assert args.playground_url == "http://127.0.0.1:7860"
        sink = build_sink_from_args(args)
        assert sink.enabled is False

    def test_off_sink_does_nothing_observable(self):
        sink = build_sink_from_args(_args())  # playground_sink absent → off
        adapter = MagicMock()
        reporter = MagicMock(run_id="RID")
        with patch.object(requests, "post") as mock_post, patch(
            "cli.playground_sink.threading.Thread"
        ) as mock_thread, patch("cli.playground_sink.build_step_event") as mock_build:
            maybe_push_step(
                sink,
                args=_args(),
                reporter=reporter,
                adapter=adapter,
                action_data=_action_data(),
                result=_result(),
                step_index=1,
            )
        # Zero side effects: no event built, no screenshot, no thread, no HTTP.
        mock_build.assert_not_called()
        adapter.take_screenshot.assert_not_called()
        mock_thread.assert_not_called()
        mock_post.assert_not_called()

    def test_explicit_flag_enables(self):
        from cli.parser import build_parser

        args = build_parser().parse_args(
            [
                "--action",
                "click",
                "--locator-type",
                "text",
                "--locator-value",
                "x",
                "--playground-sink",
                "--playground-url",
                "http://example:1234",
            ]
        )
        sink = build_sink_from_args(args)
        assert sink.enabled is True
        assert sink.base_url == "http://example:1234"


class _FakeAdapter:
    """A no-browser adapter: read-only screenshot, no teardown side effects."""

    def __init__(self):
        self.driver = object()

    def take_screenshot(self):
        return b"\x89PNG\r\n\x1a\n"  # minimal PNG header; non-empty so it encodes

    def teardown(self):
        pass


class _FakeExecutor:
    """Returns a successful step so the action reaches save_to_disk + the sink."""

    def __init__(self, *a, **k):
        pass

    def execute_and_record(self, action_data):
        return {
            "success": True,
            "code_lines": ["    with allure.step('x'):\n", "        d.click()\n"],
            "action_description": action_data.get("name", "x"),
            "error_code": "",
        }


class TestExitCodeContractEndToEnd:
    """Red line #1, end-to-end: a bare --action with --playground-sink pointed at a
    DEAD port must still exit 0 (success) and not stall — the headline contract is
    the 0/1 exit code, not merely 'the sink doesn't raise'. This drives the REAL
    run_action_default_mode success path (real sink → real daemon thread → real
    requests.post to a closed port → real join_on_exit → real `return 0`); only the
    browser adapter/executor are faked, so a future call-site regression that let
    the bypass change the exit code or block the process would fail HERE."""

    def _args(self, port_url):
        from cli.parser import build_parser

        return build_parser().parse_args(
            [
                "--action", "click",
                "--locator-type", "text",
                "--locator-value", "x",
                "--platform", "web",
                "--playground-sink",
                "--playground-url", port_url,
            ]
        )

    def _run(self, tmp_path, monkeypatch, port_url):
        import time

        import cli.modes.action as action_mode
        import config.config as cfg
        from cli.shared import _SharedAdapterManager

        # Hermetic: reporter writes under tmp_path, not the repo's report/runs.
        monkeypatch.setattr(cfg, "RUN_REPORT_BASE_DIR", tmp_path / "runs", raising=False)

        mgr = _SharedAdapterManager()
        adapter = _FakeAdapter()
        monkeypatch.setattr(mgr, "get_or_create", lambda platform, env="dev": adapter)
        monkeypatch.setattr(mgr, "get_executor", lambda platform, env="dev": _FakeExecutor())
        # The success-path --json branch re-captures UI; keep it inert (no browser).
        monkeypatch.setattr(action_mode, "_capture_ui_state",
                            lambda args, ad, rep, step: ('{"ui_elements":[]}', None))

        out_script = str(tmp_path / "test_auto.py")
        start = time.perf_counter()
        code = action_mode.run_action_default_mode(
            self._args(port_url), out_script, {}, shared_adapter_manager=mgr
        )
        elapsed = time.perf_counter() - start
        return code, elapsed

    def test_dead_port_sink_still_exits_zero_and_is_bounded(self, tmp_path, monkeypatch):
        # 127.0.0.1:9 (discard) — refuses fast; the success path must return 0.
        code, elapsed = self._run(tmp_path, monkeypatch, "http://127.0.0.1:9")
        assert code == 0, "sink to a dead port must NOT change the success exit code"
        # join_on_exit=True caps added latency; a refused connect is near-instant.
        assert elapsed < 2.0, f"action path stalled {elapsed:.2f}s behind the sink"

    def test_exit_code_identical_with_sink_off(self, tmp_path, monkeypatch):
        # The same success path with the flag absent must yield the same exit code:
        # the bypass observer is invisible to the contract whether on or off.
        on, _ = self._run(tmp_path, monkeypatch, "http://127.0.0.1:9")

        import cli.modes.action as action_mode
        import config.config as cfg
        from cli.parser import build_parser
        from cli.shared import _SharedAdapterManager

        monkeypatch.setattr(cfg, "RUN_REPORT_BASE_DIR", tmp_path / "runs2", raising=False)
        mgr = _SharedAdapterManager()
        adapter = _FakeAdapter()
        monkeypatch.setattr(mgr, "get_or_create", lambda platform, env="dev": adapter)
        monkeypatch.setattr(mgr, "get_executor", lambda platform, env="dev": _FakeExecutor())
        monkeypatch.setattr(action_mode, "_capture_ui_state",
                            lambda args, ad, rep, step: ('{"ui_elements":[]}', None))
        off_args = build_parser().parse_args(
            ["--action", "click", "--locator-type", "text", "--locator-value", "x",
             "--platform", "web"]
        )
        off = action_mode.run_action_default_mode(
            off_args, str(tmp_path / "off.py"), {}, shared_adapter_manager=mgr
        )
        assert on == off == 0, "exit code must be identical with the sink on vs off"
