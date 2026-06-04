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

# A page with a deferred element + a pre-filled input + a removable node, so the
# P1 assertions (contains/value/not_exist) and wait_for can be exercised against
# REAL async DOM behavior — the only way to prove auto-retry actually polls.
_DYNAMIC_PAGE = (
    "data:text/html,"
    "<input id='email' value='admin@test.com'>"
    "<p id='greeting'>Welcome back, Alice</p>"
    "<div id='doomed'>temporary</div>"
    "<span id='late'></span>"
    "<script>"
    "setTimeout(function(){document.getElementById('late').textContent='loaded-late';}, 700);"
    "setTimeout(function(){document.getElementById('doomed').remove();}, 700);"
    "</script>"
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


# ---------------------------------------------------------------------------
# P1: richer assertion vocabulary + wait_for, exercised on a REAL browser.
# ---------------------------------------------------------------------------

def test_real_new_assertions_execute_verdicts(live_adapter):
    """assert_text_contains / assert_value / assert_url / assert_not_exist must
    return the correct live verdict against a real DOM (the execute() path that
    feeds the autonomous loop and --json)."""
    from common.executor import UIExecutor

    live_adapter.driver.goto(_DYNAMIC_PAGE)
    ex = UIExecutor(live_adapter.driver, platform="web")

    # text_contains: substring present
    r = ex.execute_and_record({"action": "assert_text_contains", "locator_type": "css",
                               "locator_value": "#greeting", "extra_value": "Welcome"})
    assert r["success"] is True and not r.get("assertion_failed")

    # text_contains: substring absent → assertion verdict (not engine error)
    r = ex.execute_and_record({"action": "assert_text_contains", "locator_type": "css",
                               "locator_value": "#greeting", "extra_value": "Goodbye"})
    assert r["success"] is False and r.get("assertion_failed") is True

    # value: pre-filled input matches
    r = ex.execute_and_record({"action": "assert_value", "locator_type": "css",
                               "locator_value": "#email", "extra_value": "admin@test.com"})
    assert r["success"] is True and not r.get("assertion_failed")

    # url: the data: URL contains our markup verbatim (Chromium keeps literal
    # spaces in data: URLs, so assert on a space-free token that is reliably
    # present — the element id). Global action, no locator.
    r = ex.execute_and_record({"action": "assert_url", "locator_type": "global",
                               "locator_value": "global", "extra_value": "greeting"})
    assert r["success"] is True and not r.get("assertion_failed")


def test_real_wait_for_polls_until_visible(live_adapter):
    """wait_for must POLL: #late gets its text 700ms after load. A read-once
    check would miss it; a real auto-retry wait catches it. Proves the polling
    behavior that kills magic-sleep flakiness."""
    from common.executor import UIExecutor

    live_adapter.driver.goto(_DYNAMIC_PAGE)
    ex = UIExecutor(live_adapter.driver, platform="web")

    # Immediately after load #late is empty; wait_for(visible) + text_contains
    # must still succeed because expect/wait_for poll until the script fires.
    r = ex.execute_and_record({"action": "wait_for", "locator_type": "css",
                               "locator_value": "#late", "extra_value": "visible"})
    assert r["success"] is True

    r = ex.execute_and_record({"action": "assert_text_contains", "locator_type": "css",
                               "locator_value": "#late", "extra_value": "loaded-late"})
    assert r["success"] is True, "expect() did not poll until the late text arrived"


def test_real_assert_not_exist_waits_for_removal(live_adapter):
    """assert_not_exist must pass once #doomed is removed (700ms after load) —
    proving to_be_hidden polls rather than reading once."""
    from common.executor import UIExecutor

    live_adapter.driver.goto(_DYNAMIC_PAGE)
    ex = UIExecutor(live_adapter.driver, platform="web")

    r = ex.execute_and_record({"action": "assert_not_exist", "locator_type": "css",
                               "locator_value": "#doomed", "extra_value": ""})
    assert r["success"] is True, "assert_not_exist did not wait for the node to be removed"


def test_real_generated_assertions_are_runnable(live_adapter):
    """THE headline contract: the pytest code we EMIT must actually run green on
    a real page. We generate the body for several P1 assertions, wrap it in a
    function whose only fixture `d` is the live page, exec it, and call it. If
    the emitted expect()/wait_for lines are malformed or wrong, this raises."""
    from common.executor import (
        AssertNotExistHandler,
        AssertTextContainsHandler,
        AssertUrlHandler,
        AssertValueHandler,
        WaitForHandler,
    )

    live_adapter.driver.goto(_DYNAMIC_PAGE)

    body = []
    body += WaitForHandler().generate_code("web", "css", "#late", "visible", 30.0)
    body += AssertTextContainsHandler().generate_code("web", "css", "#greeting", "Welcome", 30.0)
    body += AssertValueHandler().generate_code("web", "css", "#email", "admin@test.com", 30.0)
    body += AssertUrlHandler().generate_code("web", "global", "global", "greeting", 30.0)
    body += AssertNotExistHandler().generate_code("web", "css", "#doomed", "", 30.0)

    # Build a real, importable function: `def _gen(d):` + the emitted step lines.
    src = "import allure\nfrom common.logs import log\n\ndef _gen(d):\n" + "".join(body)
    ns: dict = {}
    exec(compile(src, "<generated>", "exec"), ns)  # noqa: S102 — exercising our own codegen
    # Run the generated steps against the real page. Any malformed/failing
    # assertion raises here and fails the test.
    ns["_gen"](live_adapter.driver)
