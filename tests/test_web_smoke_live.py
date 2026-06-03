"""Live web smoke test — real Chromium, no mocks.

WHY THIS EXISTS: during the 2026-06 audit, the T2 "web recording" fix passed its
mocked unit test while being completely broken on real hardware (the mock forced
a code path that CDP never reaches). Mocks proved "the code calls the right
args"; only a real browser proved "the feature actually works". This smoke
exercises the audit-touched paths against a real Playwright/Chromium session so
that class of "mock-green, real-broken" regression fails loudly.

OPT-IN: skipped by default (needs a real browser + ~seconds of runtime). Enable:

    RUN_LIVE_WEB_SMOKE=1 pytest tests/test_web_smoke_live.py -v

It self-skips if Playwright/Chromium isn't installed, so it never breaks a
core-only environment.
"""

import os

import pytest

_RUN = os.getenv("RUN_LIVE_WEB_SMOKE", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live_web,
    pytest.mark.skipif(
        not _RUN,
        reason="Live web smoke is opt-in. Set RUN_LIVE_WEB_SMOKE=1 to run (needs real Chromium).",
    ),
]

# data: URL keeps the test offline and deterministic — no network dependency.
_PAGE = (
    "data:text/html,"
    "<h1>Smoke Heading</h1>"
    "<button id='go'>Click Me</button>"
    "<p>present paragraph</p>"
)


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


@pytest.fixture
def live_adapter():
    if not _chromium_available():
        pytest.skip("Playwright/Chromium not installed")

    from common.adapters.web_adapter import WebPlaywrightAdapter, stop_persistent_browser

    # Start clean so we exercise a real launch, and clean up the persistent
    # browser afterwards so the test leaves no orphaned Chromium (T9).
    stop_persistent_browser()
    adapter = WebPlaywrightAdapter()
    adapter.setup()
    try:
        yield adapter
    finally:
        try:
            adapter.teardown()
        except Exception:
            pass
        stop_persistent_browser()


def test_real_launch_and_inspect_then_ref_resolves(live_adapter):
    """T2 (real launch) + T13 (inspect syncs ref cache → ref resolves on live page)."""
    import json

    from common.executor import UIExecutor
    from utils.utils_web import compress_web_dom

    live_adapter.driver.goto(_PAGE)
    live_adapter.driver.wait_for_timeout(300)

    # Real DOM compression (not a fixture) — must find our interactive elements.
    tree = json.loads(compress_web_dom(live_adapter.driver))
    elements = tree.get("ui_elements", [])
    assert elements, "live DOM compression returned no elements"
    assert any(e.get("id") == "go" for e in elements), "button#go not captured live"

    ref = next(e["ref"] for e in elements if e.get("id") == "go")

    # Mirror what build_inspect_ui_payload does (T13): sync the ref cache on the
    # SAME executor that will run the action, so @N resolves on this page.
    executor = UIExecutor(live_adapter.driver, platform="web")
    executor.set_ui_elements(elements)

    # A real ref-based click must resolve against the live page and succeed.
    result = executor.execute_and_record(
        {"action": "click", "locator_type": "ref", "locator_value": ref, "extra_value": ""}
    )
    assert result["success"] is True, f"ref click {ref} failed on live page"


def test_real_assert_pass_and_fail_contract(live_adapter):
    """T4: assert_exist returns the real verdict against a live DOM."""
    from common.executor import UIExecutor

    live_adapter.driver.goto(_PAGE)
    live_adapter.driver.wait_for_timeout(300)
    executor = UIExecutor(live_adapter.driver, platform="web")

    present = executor.execute_and_record(
        {"action": "assert_exist", "locator_type": "text",
         "locator_value": "present paragraph", "extra_value": ""}
    )
    assert present["success"] is True
    assert not present.get("assertion_failed")

    absent = executor.execute_and_record(
        {"action": "assert_exist", "locator_type": "text",
         "locator_value": "definitely-not-on-this-page-zzz", "extra_value": ""}
    )
    assert absent["success"] is False
    assert absent.get("assertion_failed") is True


def test_real_web_recording_is_unsupported_not_crashing(live_adapter):
    """T2 (corrected): web recording is a no-op returning "" — and never crashes
    on driver.video (the original AttributeError bug)."""
    live_adapter.driver.goto(_PAGE)
    live_adapter.driver.wait_for_timeout(200)
    # Must not raise, must return "" (recording impossible over CDP).
    assert live_adapter.stop_record_and_get_path("report/videos_web/never.webm") == ""


def test_real_web_stop_kills_live_browser(live_adapter):
    """T9: --web-stop terminates the real detached Chromium and clears the session."""
    import common.adapters.web_adapter as wa

    session = wa._read_session()
    assert session and session.get("pid"), "expected a persistent browser session file"
    pid = session["pid"]
    assert wa._is_process_alive(pid), "persistent Chromium should be alive after setup"

    assert wa.stop_persistent_browser() is True
    live_adapter.driver = None  # teardown shouldn't try to use the killed browser

    import time
    time.sleep(0.5)
    assert not wa._is_process_alive(pid), "Chromium still alive after --web-stop (leak!)"
    assert wa._read_session() is None, "session file not cleared after --web-stop"
