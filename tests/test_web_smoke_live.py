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
from urllib.parse import quote as _quote

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


# ---------------------------------------------------------------------------
# P2: codegen quality on a REAL browser — goal-named tests, coordinate honesty.
# ---------------------------------------------------------------------------

# A page with a button that has NO id and NO direct text (text is in a child
# span), but DOES have an accessible name via aria-label — so the @N id/text
# chain misses it, forcing the runtime to recover a get_by_role/label locator
# instead of a coordinate.
_NAMELESS_BUTTON_PAGE = (
    "data:text/html,"
    "<button aria-label='Save document'><span>💾</span></button>"
    # name-only input, NO value/id/text → only locatable by [name=], so a ref
    # action must recover via the name-based locator (exercises the fallback).
    "<input name='token'>"
)


def test_real_goal_named_generated_file_runs_green(live_adapter):
    """A full generated file named after the user's goal must be valid, runnable
    pytest. We build header(label=...) + a real assertion step, exec it, and run
    it against the live page — proving goal-naming doesn't break runnability."""
    from cli.shared import get_initial_header
    from common.executor import AssertTextContainsHandler

    live_adapter.driver.goto(_DYNAMIC_PAGE)

    header = get_initial_header(label="登录后看到欢迎语")  # Chinese goal — the common case
    body = AssertTextContainsHandler().generate_code("web", "css", "#greeting", "Welcome", 30.0)
    src = "".join(header) + "".join(body)

    # The whole file must parse and define a goal-named test function.
    ns: dict = {}
    exec(compile(src, "<generated>", "exec"), ns)  # noqa: S102
    test_fns = [k for k in ns if k.startswith("test_")]
    assert test_fns, "no test_ function emitted"
    assert test_fns[0] != "test_auto_generated_case", "goal label did not name the test"
    # And it runs green against the live page.
    ns[test_fns[0]](live_adapter.driver)


def test_real_coordinate_fallback_recovers_locator_not_pixels(live_adapter):
    """Coordinate-honesty: a ref locatable only by name/role (id+text both miss)
    must be recovered to a STABLE locator at runtime — the persisted code_lines
    must contain a get_by_role/get_by_label/[name=] click, NOT a mouse.click,
    and that emitted locator must actually run green on the live page."""
    import json

    from common.executor import UIExecutor
    from utils.utils_web import compress_web_dom

    live_adapter.driver.goto(_NAMELESS_BUTTON_PAGE)
    live_adapter.driver.wait_for_timeout(200)

    tree = json.loads(compress_web_dom(live_adapter.driver))
    elements = tree.get("ui_elements", [])
    # Find the aria-label button ref — it has `desc` but no id and no direct text.
    btn = next((e for e in elements if e.get("desc") == "Save document"), None)
    assert btn is not None, "aria-label button not captured"
    assert not btn.get("id"), "fixture button unexpectedly has an id"

    ex = UIExecutor(live_adapter.driver, platform="web")
    ex.set_ui_elements(elements)
    result = ex.execute_and_record(
        {"action": "click", "locator_type": "ref", "locator_value": btn["ref"], "extra_value": ""}
    )
    assert result["success"] is True
    emitted = "".join(result["code_lines"])
    assert "mouse.click" not in emitted, "coordinate click leaked into persisted test"
    assert ("get_by_role" in emitted or "get_by_label" in emitted), \
        f"expected a recovered semantic locator, got:\n{emitted}"

    # The recovered locator must itself run green on the live page.
    src = "import allure\nfrom common.logs import log\n\ndef _gen(d):\n" + emitted
    ns: dict = {}
    exec(compile(src, "<generated>", "exec"), ns)  # noqa: S102
    ns["_gen"](live_adapter.driver)


def test_real_ref_input_recovers_locator_not_misclicked(live_adapter):
    """Regression for the non-click-through-fallback bug: an `input` on a ref
    that resolves only by `name` (id+text both miss) must TYPE the text via a
    recovered [name=] locator — NOT get silently mis-executed as a click with
    the text dropped. Verifies both the live effect and the emitted code."""
    import json

    from common.executor import UIExecutor
    from utils.utils_web import compress_web_dom

    # The token input has a name but no id; aria-label button gives it no text.
    live_adapter.driver.goto(_NAMELESS_BUTTON_PAGE)
    live_adapter.driver.wait_for_timeout(200)
    tree = json.loads(compress_web_dom(live_adapter.driver))
    elements = tree.get("ui_elements", [])
    field = next((e for e in elements if e.get("name") == "token"), None)
    assert field is not None and not field.get("id"), "name-only token input not captured"

    ex = UIExecutor(live_adapter.driver, platform="web")
    ex.set_ui_elements(elements)
    result = ex.execute_and_record(
        {"action": "input", "locator_type": "ref", "locator_value": field["ref"],
         "extra_value": "typed-value-xyz"}
    )
    assert result["success"] is True
    emitted = "".join(result["code_lines"])
    # Must be a real fill via a recovered locator, never a mouse.click, never a skip.
    assert "mouse.click" not in emitted, "input was mis-executed as a coordinate click"
    assert "pytest.skip" not in emitted, "name-locatable input wrongly discarded as unreplayable"
    assert ".fill(" in emitted and "typed-value-xyz" in emitted, f"text not typed:\n{emitted}"
    # And the live field actually holds the typed value.
    assert live_adapter.driver.locator('[name="token"]').input_value() == "typed-value-xyz"


def test_real_ref_click_label_has_no_stale_at_token(live_adapter):
    """The allure.step label for a web ref click must show the readable target,
    not a raw @N (humanize_step_labels wired through execute_and_record)."""
    import json

    from common.executor import UIExecutor
    from utils.utils_web import compress_web_dom

    live_adapter.driver.goto(_PAGE)  # has <button id='go'>Click Me</button>
    live_adapter.driver.wait_for_timeout(200)
    tree = json.loads(compress_web_dom(live_adapter.driver))
    elements = tree.get("ui_elements", [])
    ref = next(e["ref"] for e in elements if e.get("id") == "go")

    ex = UIExecutor(live_adapter.driver, platform="web")
    ex.set_ui_elements(elements)
    result = ex.execute_and_record(
        {"action": "click", "locator_type": "ref", "locator_value": ref, "extra_value": ""}
    )
    assert result["success"] is True
    emitted = "".join(result["code_lines"])
    assert f"[{ref}]" not in emitted, f"stale ref token {ref} leaked into the allure.step label"


# ---------------------------------------------------------------------------
# P3a: richer web interaction actions on a REAL browser.
# ---------------------------------------------------------------------------

# A form page exercising select, double-click, right-click, scroll, and drag.
# JS records interaction outcomes into #log so the test can assert real effects.
# URL-encoded: unencoded inline JS (the ',', '{', etc.) truncates a data: URL in
# Chromium, so the elements would silently never exist.
_FORM_PAGE = "data:text/html," + _quote(
    "<select id='country'><option value='us'>US</option>"
    "<option value='jp'>Japan</option></select>"
    "<div id='dbl'>dbl-target</div>"
    "<div id='ctx'>ctx-target</div>"
    "<div style='height:1500px'>spacer</div>"
    "<button id='far'>Far Button</button>"
    "<div id='log'></div>"
    "<script>"
    "document.getElementById('dbl').ondblclick=function(){document.getElementById('log').textContent='dbl-fired';};"
    "document.getElementById('ctx').oncontextmenu=function(e){e.preventDefault();document.getElementById('log').textContent='ctx-fired';};"
    "</script>"
)


def _run_generated(driver, code_lines):
    """Compile + run emitted step lines against the live page, as a real test
    file would. Raises on any malformed or failing generated line."""
    src = "import allure\nfrom common.logs import log\n\ndef _gen(d):\n" + "".join(code_lines)
    ns: dict = {}
    exec(compile(src, "<generated>", "exec"), ns)  # noqa: S102 — exercising our own codegen
    ns["_gen"](driver)


def test_real_select_option(live_adapter):
    """select must change a native <select> AND its emitted code must run green."""
    from common.executor import UIExecutor

    live_adapter.driver.goto(_FORM_PAGE)
    ex = UIExecutor(live_adapter.driver, platform="web")
    result = ex.execute_and_record(
        {"action": "select", "locator_type": "css", "locator_value": "#country", "extra_value": "jp"}
    )
    assert result["success"] is True
    assert live_adapter.driver.locator("#country").input_value() == "jp"
    # Reset, then prove the EMITTED code reproduces the selection.
    live_adapter.driver.goto(_FORM_PAGE)
    _run_generated(live_adapter.driver, result["code_lines"])
    assert live_adapter.driver.locator("#country").input_value() == "jp"


def test_real_double_click(live_adapter):
    from common.executor import UIExecutor

    live_adapter.driver.goto(_FORM_PAGE)
    ex = UIExecutor(live_adapter.driver, platform="web")
    result = ex.execute_and_record(
        {"action": "double_click", "locator_type": "css", "locator_value": "#dbl", "extra_value": ""}
    )
    assert result["success"] is True
    assert live_adapter.driver.locator("#log").inner_text() == "dbl-fired"
    _run_generated(live_adapter.driver, result["code_lines"])  # emitted code is runnable


def test_real_right_click(live_adapter):
    from common.executor import UIExecutor

    live_adapter.driver.goto(_FORM_PAGE)
    ex = UIExecutor(live_adapter.driver, platform="web")
    result = ex.execute_and_record(
        {"action": "right_click", "locator_type": "css", "locator_value": "#ctx", "extra_value": ""}
    )
    assert result["success"] is True
    assert live_adapter.driver.locator("#log").inner_text() == "ctx-fired"
    _run_generated(live_adapter.driver, result["code_lines"])


def test_real_scroll_into_view(live_adapter):
    from common.executor import UIExecutor

    live_adapter.driver.goto(_FORM_PAGE)
    ex = UIExecutor(live_adapter.driver, platform="web")
    result = ex.execute_and_record(
        {"action": "scroll_into_view", "locator_type": "css", "locator_value": "#far", "extra_value": ""}
    )
    assert result["success"] is True
    # The far button is now in the viewport.
    assert live_adapter.driver.locator("#far").is_visible()
    _run_generated(live_adapter.driver, result["code_lines"])


def test_real_upload(live_adapter, tmp_path):
    from common.executor import UIExecutor

    f = tmp_path / "upload.txt"
    f.write_text("hello")
    page = "data:text/html," + _quote(
        "<input id='file' type='file'>"
        "<div id='log'></div>"
        "<script>document.getElementById('file').onchange=function(e){"
        "document.getElementById('log').textContent=e.target.files[0].name;};</script>"
    )
    live_adapter.driver.goto(page)
    ex = UIExecutor(live_adapter.driver, platform="web")
    result = ex.execute_and_record(
        {"action": "upload", "locator_type": "css", "locator_value": "#file", "extra_value": str(f)}
    )
    assert result["success"] is True
    assert live_adapter.driver.locator("#log").inner_text() == "upload.txt"


def test_real_drag(live_adapter):
    from common.executor import UIExecutor

    # Pointer-based drag (mousedown→move→mouseup) — the model Playwright's
    # drag_to actually drives. The inline JS MUST be URL-encoded or Chromium
    # truncates the data: URL and the elements never exist.
    page = "data:text/html," + _quote(
        "<div id='src' style='width:80px;height:80px;background:#ccc'>SRC</div>"
        "<div id='dst' style='width:120px;height:120px;background:#eee'>DST</div>"
        "<div id='log'></div>"
        "<script>"
        "var s=document.getElementById('src'),d=document.getElementById('dst');"
        "s.addEventListener('mousedown',function(){window.__dragging=true;});"
        "d.addEventListener('mouseup',function(){if(window.__dragging){"
        "document.getElementById('log').textContent='dropped';window.__dragging=false;}});"
        "</script>"
    )
    live_adapter.driver.goto(page)
    ex = UIExecutor(live_adapter.driver, platform="web")
    result = ex.execute_and_record(
        {"action": "drag", "locator_type": "css", "locator_value": "#src", "extra_value": "#dst"}
    )
    assert result["success"] is True
    assert live_adapter.driver.locator("#log").inner_text() == "dropped"
    emitted = "".join(result["code_lines"])
    assert "drag_to" in emitted and "#dst" in emitted
    # The emitted drag code is itself runnable on the live page.
    live_adapter.driver.goto(page)
    _run_generated(live_adapter.driver, result["code_lines"])
    assert live_adapter.driver.locator("#log").inner_text() == "dropped"
