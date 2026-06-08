"""Tests for cli/playground_sink.py — the fire-and-forget visualization sink.

Red line under test (G5): a sink push that fails MUST NOT raise, slow down, or
change the exit code of the action path. These tests pin that contract plus the
cross-process run-key resolution (arch#1) and daemon non-blocking (arch#3).
"""

import argparse
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from cli.playground_sink import (
    DEFAULT_PLAYGROUND_URL,
    PlaygroundSink,
    PlaygroundStepEvent,
    build_sink_from_args,
    build_step_event,
    maybe_push_step,
    resolve_playground_run_key,
)


def _result(success=True):
    return {
        "success": success,
        "code_lines": ["    with allure.step('点击登录'):\n", "        d.click()\n"],
        "action_description": "点击登录",
        "error_code": "",
    }


def _action_data():
    return {
        "name": "点击登录",
        "action": "click",
        "locator_type": "text",
        "locator_value": "登录",
        "extra_value": "",
    }


class TestStepEventModel:
    """#1 — pydantic shape: required run_id/step_index, sane defaults."""

    def test_minimal_required_fields(self):
        ev = PlaygroundStepEvent(run_id="r1", step_index=1)
        assert ev.run_id == "r1"
        assert ev.step_index == 1
        assert ev.code_lines == []
        assert ev.action_description == ""
        assert ev.action == ""
        assert ev.locator_type == ""
        assert ev.locator_value == ""
        assert ev.extra_value == ""
        assert ev.success is True
        assert ev.screenshot_b64 == ""

    def test_run_id_required(self):
        with pytest.raises(Exception):
            PlaygroundStepEvent(step_index=1)

    def test_step_index_required(self):
        with pytest.raises(Exception):
            PlaygroundStepEvent(run_id="r1")

    def test_model_dump_is_json_serializable(self):
        ev = PlaygroundStepEvent(run_id="r1", step_index=2, code_lines=["a\n"])
        dumped = ev.model_dump()
        assert dumped["run_id"] == "r1"
        assert dumped["step_index"] == 2
        assert dumped["code_lines"] == ["a\n"]


class TestPushStepDisabled:
    """#2 — enabled=False: zero HTTP, and crucially no thread spawned."""

    def test_disabled_sink_sends_nothing(self):
        sink = PlaygroundSink(enabled=False)
        ev = PlaygroundStepEvent(run_id="r1", step_index=1)
        with patch.object(requests, "post") as mock_post, patch(
            "cli.playground_sink.threading.Thread"
        ) as mock_thread:
            sink.push_step(ev)
            mock_post.assert_not_called()
            mock_thread.assert_not_called()


class TestPushStepSilentDegrade:
    """#3/#4 — playground unreachable or hung: _post never raises (G5)."""

    def test_connection_error_swallowed(self):
        sink = PlaygroundSink(enabled=True)
        ev = PlaygroundStepEvent(run_id="r1", step_index=1)
        with patch.object(
            requests, "post", side_effect=requests.exceptions.ConnectionError("refused")
        ):
            # Must not raise.
            sink._post(ev)

    def test_timeout_swallowed(self):
        sink = PlaygroundSink(enabled=True)
        ev = PlaygroundStepEvent(run_id="r1", step_index=1)
        with patch.object(
            requests, "post", side_effect=requests.exceptions.Timeout("slow")
        ):
            sink._post(ev)

    def test_post_uses_split_timeout(self):
        """Connect/read timeouts are split so a hung playground can't stall the path."""
        from cli.playground_sink import _POST_TIMEOUT

        sink = PlaygroundSink(enabled=True)
        ev = PlaygroundStepEvent(run_id="r1", step_index=1)
        with patch.object(requests, "post") as mock_post:
            sink._post(ev)
            _, kwargs = mock_post.call_args
            assert kwargs["timeout"] == _POST_TIMEOUT
            # connect+read budget must stay tight (red line #1: don't slow the action)
            assert sum(kwargs["timeout"]) <= 0.6
            assert kwargs["json"]["run_id"] == "r1"


class TestEncodeScreenshot:
    """#5 — encode_screenshot: bytes→base64; None/raise→'' (degrade)."""

    def test_encodes_bytes(self):
        adapter = MagicMock()
        adapter.take_screenshot.return_value = b"\x89PNG\r\n"
        b64 = PlaygroundSink.encode_screenshot(adapter)
        assert b64
        import base64

        assert base64.b64decode(b64) == b"\x89PNG\r\n"

    def test_none_returns_empty(self):
        adapter = MagicMock()
        adapter.take_screenshot.return_value = None
        assert PlaygroundSink.encode_screenshot(adapter) == ""

    def test_exception_returns_empty(self):
        adapter = MagicMock()
        adapter.take_screenshot.side_effect = RuntimeError("connection lost")
        assert PlaygroundSink.encode_screenshot(adapter) == ""


class TestBuildStepEventFactory:
    """#6 — mandatory single construction point assembles all eight fields."""

    def test_assembles_all_fields(self):
        ev = build_step_event(
            run_key="run-A",
            step_index=3,
            action_data=_action_data(),
            result=_result(),
            screenshot_b64="ZHVtbXk=",
        )
        assert ev.run_id == "run-A"
        assert ev.step_index == 3
        assert ev.code_lines == _result()["code_lines"]
        assert ev.action_description == "点击登录"
        assert ev.action == "click"
        assert ev.locator_type == "text"
        assert ev.locator_value == "登录"
        assert ev.extra_value == ""
        assert ev.success is True
        assert ev.screenshot_b64 == "ZHVtbXk="

    def test_tolerates_missing_optional_action_keys(self):
        ev = build_step_event(
            run_key="r",
            step_index=1,
            action_data={"action": "swipe"},
            result=_result(),
            screenshot_b64="",
        )
        assert ev.action == "swipe"
        assert ev.locator_type == ""
        assert ev.locator_value == ""


class TestResolveRunKey:
    """#13 — run-key contract (arch#1): the seed's cross-process correctness.

    A bare --action is a single step. A --session-id groups N short-lived
    processes into ONE timeline: same run_key, step_index increments via the
    session's persisted 'steps' counter (incremented post-success in dispatch).
    """

    def test_session_id_gives_stable_key_incrementing_index(self):
        args = argparse.Namespace(session_id="s1", session_end="")
        reporter = MagicMock(run_id="RID-unused")
        with patch("cli.playground_sink.load_session") as mock_load:
            mock_load.return_value = {"steps": 0}
            assert resolve_playground_run_key(args, reporter) == ("s1", 1)
            mock_load.return_value = {"steps": 1}
            assert resolve_playground_run_key(args, reporter) == ("s1", 2)
            mock_load.return_value = {"steps": 2}
            assert resolve_playground_run_key(args, reporter) == ("s1", 3)

    def test_session_id_missing_session_defaults_to_one(self):
        args = argparse.Namespace(session_id="s1", session_end="")
        reporter = MagicMock(run_id="RID")
        with patch("cli.playground_sink.load_session", return_value=None):
            assert resolve_playground_run_key(args, reporter) == ("s1", 1)

    def test_no_session_uses_reporter_run_id_step_one(self):
        args = argparse.Namespace(session_id="", session_end="")
        reporter = MagicMock(run_id="20260608_ab12cd34")
        # load_session must not even be consulted on the bare path.
        with patch("cli.playground_sink.load_session") as mock_load:
            assert resolve_playground_run_key(args, reporter) == ("20260608_ab12cd34", 1)
            mock_load.assert_not_called()

    def test_missing_session_attrs_fall_back_gracefully(self):
        args = argparse.Namespace()  # no session_id / session_end at all
        reporter = MagicMock(run_id="RID")
        assert resolve_playground_run_key(args, reporter) == ("RID", 1)


class TestDaemonNonBlocking:
    """#14 — a hung push must not stall the action's hot path (arch#3)."""

    def test_push_step_returns_immediately_under_slow_post(self):
        sink = PlaygroundSink(enabled=True, join_on_exit=False)
        ev = PlaygroundStepEvent(run_id="r1", step_index=1)

        def _slow_post(*a, **k):
            time.sleep(2.0)
            return MagicMock()

        with patch.object(requests, "post", side_effect=_slow_post):
            start = time.perf_counter()
            sink.push_step(ev)
            elapsed = time.perf_counter() - start
        # Daemon thread carries the 2s sleep; the caller returns near-instantly.
        assert elapsed < 0.3, f"push_step blocked for {elapsed:.2f}s"

    def test_single_step_join_is_bounded_under_slow_alive_playground(self):
        """HIGH-1 guard: --action uses join_on_exit=True. A reachable-but-slow
        playground must NOT tax the contract path beyond the documented ceiling.
        Pins the join window so it can't silently grow back to 0.6s+."""
        from cli.playground_sink import _JOIN_TIMEOUT

        assert _JOIN_TIMEOUT <= 0.35, "join ceiling crept up — red line #1 (don't slow the action)"
        sink = PlaygroundSink(enabled=True, join_on_exit=True)
        ev = PlaygroundStepEvent(run_id="r1", step_index=1)

        def _slow_post(*a, **k):
            time.sleep(5.0)  # alive but very slow
            return MagicMock()

        with patch.object(requests, "post", side_effect=_slow_post):
            start = time.perf_counter()
            sink.push_step(ev)
            elapsed = time.perf_counter() - start
        # Bounded by the join ceiling (+ a little scheduling slack), NOT the 5s post.
        assert elapsed < _JOIN_TIMEOUT + 0.25, f"single-step path blocked {elapsed:.2f}s"

    def test_default_url(self):
        assert DEFAULT_PLAYGROUND_URL == "http://127.0.0.1:7860"
        sink = PlaygroundSink()
        assert sink.base_url == "http://127.0.0.1:7860"
        assert sink.enabled is False


class TestBuildSinkFromArgs:
    """dispatch.py constructs the sink from CLI flags (or env, for main.py)."""

    def test_enabled_from_flag(self):
        args = argparse.Namespace(
            playground_sink=True, playground_url="http://host:9000"
        )
        sink = build_sink_from_args(args, join_on_exit=True)
        assert sink.enabled is True
        assert sink.base_url == "http://host:9000"
        assert sink._join_on_exit is True

    def test_disabled_by_default(self):
        args = argparse.Namespace()  # neither flag present
        sink = build_sink_from_args(args)
        assert sink.enabled is False
        assert sink.base_url == DEFAULT_PLAYGROUND_URL


class TestMaybePushStep:
    """#10 — the single guarded entry point all 3 call sites use.

    The contract: when the sink is disabled it returns BEFORE touching the
    adapter — take_screenshot must never be called (zero cost + no device I/O on
    the hot path). When enabled it builds via the factory and pushes once.
    """

    def test_disabled_never_touches_adapter_or_network(self):
        sink = PlaygroundSink(enabled=False)
        adapter = MagicMock()
        args = argparse.Namespace(session_id="", session_end="", platform="web")
        reporter = MagicMock(run_id="RID")
        with patch.object(requests, "post") as mock_post, patch(
            "cli.playground_sink.threading.Thread"
        ) as mock_thread:
            maybe_push_step(
                sink,
                args=args,
                reporter=reporter,
                adapter=adapter,
                action_data=_action_data(),
                result=_result(),
                step_index=1,
            )
        adapter.take_screenshot.assert_not_called()  # zero device I/O when off
        mock_post.assert_not_called()
        mock_thread.assert_not_called()

    def test_enabled_builds_and_pushes_once(self):
        sink = PlaygroundSink(enabled=True)
        adapter = MagicMock()
        adapter.take_screenshot.return_value = b"\x89PNG"
        args = argparse.Namespace(session_id="", session_end="", platform="web")
        reporter = MagicMock(run_id="RID-xyz")
        captured = {}

        def _capture(event):
            captured["event"] = event

        with patch.object(sink, "push_step", side_effect=_capture) as mock_push:
            maybe_push_step(
                sink,
                args=args,
                reporter=reporter,
                adapter=adapter,
                action_data=_action_data(),
                result=_result(),
                step_index=1,
            )
            mock_push.assert_called_once()
        ev = captured["event"]
        assert ev.run_id == "RID-xyz"
        assert ev.step_index == 1
        assert ev.action == "click"
        assert ev.code_lines == _result()["code_lines"]
        assert ev.screenshot_b64  # screenshot was encoded

    def test_enabled_explicit_step_index_overrides_resolver(self):
        """Workflow mode passes its own loop counter as step_index."""
        sink = PlaygroundSink(enabled=True)
        adapter = MagicMock()
        adapter.take_screenshot.return_value = b"x"
        args = argparse.Namespace(session_id="", session_end="", platform="web")
        reporter = MagicMock(run_id="RID")
        captured = {}
        with patch.object(sink, "push_step", side_effect=lambda e: captured.update(e=e)):
            maybe_push_step(
                sink,
                args=args,
                reporter=reporter,
                adapter=adapter,
                action_data=_action_data(),
                result=_result(),
                step_index=7,
            )
        assert captured["e"].step_index == 7

    def test_enabled_push_failure_never_raises(self):
        """G5 at the integration layer: a push that explodes can't break the action."""
        sink = PlaygroundSink(enabled=True)
        adapter = MagicMock()
        adapter.take_screenshot.side_effect = RuntimeError("device gone")
        args = argparse.Namespace(session_id="", session_end="", platform="web")
        reporter = MagicMock(run_id="RID")
        # Even with a broken adapter and a broken network, must not raise.
        with patch.object(
            requests, "post", side_effect=requests.exceptions.ConnectionError()
        ):
            maybe_push_step(
                sink,
                args=args,
                reporter=reporter,
                adapter=adapter,
                action_data=_action_data(),
                result=_result(),
                step_index=1,
            )
