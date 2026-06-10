"""Opt-in: prove MCP ui_agent_execute returns live observation == shell --action --json.

RUN_LIVE_WEB_SMOKE=1 to enable; self-skips without Chromium. Drives the real MCP
seam (build_tool_response_payload + a real _SharedAdapterManager) against a real
page, then asserts the response carries the live ui_tree on success and
candidates on a deliberately-bad locator.

Mirrors the opt-in guard + Chromium-availability check of tests/test_web_smoke_live.py
so it self-skips identically in a core-only / browserless environment.
"""

import os

import pytest

import cli.tool_protocol_handlers as tph
from cli.shared import _SharedAdapterManager
from common.tool_protocol import ActionToolControl, ToolRequest

_RUN = os.getenv("RUN_LIVE_WEB_SMOKE", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live_web,
    pytest.mark.skipif(
        not _RUN,
        reason="Live web smoke is opt-in. Set RUN_LIVE_WEB_SMOKE=1 to run (needs real Chromium).",
    ),
]


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        pw = sync_playwright().start()
        path = pw.chromium.executable_path
        pw.stop()
        return bool(path) and os.path.exists(path)
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _require_chromium():
    if not _chromium_available():
        pytest.skip("Playwright/Chromium not installed")


def _goto(mgr, url):
    req = ToolRequest(operation="execute", platform="web",
                      action=ActionToolControl(action="goto", extra_value=url))
    return tph.build_tool_response_payload(req, shared_adapter_manager=mgr)


def test_action_success_returns_live_uitree():
    mgr = _SharedAdapterManager()
    try:
        _goto(mgr, "https://example.com")
        req = ToolRequest(operation="execute", platform="web",
                          action=ActionToolControl(action="assert_exist",
                                                    locator_type="text",
                                                    locator_value="Example Domain"))
        resp = tph.build_tool_response_payload(req, shared_adapter_manager=mgr)
        assert resp["ok"] is True
        assert "ui_tree" in resp and resp["element_count"] >= 1
        assert resp["current_url"].startswith("https://example.com")
    finally:
        mgr.teardown_all()


def test_action_failure_returns_candidates():
    mgr = _SharedAdapterManager()
    try:
        _goto(mgr, "https://example.com")
        req = ToolRequest(operation="execute", platform="web",
                          action=ActionToolControl(action="click",
                                                    locator_type="text",
                                                    locator_value="Exmaple Doman"))  # typo
        resp = tph.build_tool_response_payload(req, shared_adapter_manager=mgr)
        assert resp["ok"] is False
        assert resp["result"] == "engine_error"
        assert "candidates" in resp  # did-you-mean surfaced
        assert resp["failure_diagnosis"]["error_code"]  # real, non-empty
    finally:
        mgr.teardown_all()
