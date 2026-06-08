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
