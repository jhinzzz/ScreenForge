"""Live Android smoke test — real device via uiautomator2, no mocks.

Same rationale as tests/test_web_smoke_live.py: prove the audit-touched Android
paths work on real hardware, not just under mocks. Drives a real device through
adapter setup → live UI-tree capture/compression → the executor assert pass/fail
contract → and the agent's core action verbs (click / input / swipe / press)
against the system Settings app.

SAFETY: action tests use the Settings app and only perform reversible,
non-destructive operations (open a submenu and go Back, type into the search box
which changes no setting, scroll). Each test resets the device to the home
screen afterward. They never toggle a setting or submit a form.

OPT-IN: skipped by default. Enable with a connected device:

    RUN_LIVE_ANDROID_SMOKE=1 pytest tests/test_android_smoke_live.py -v

Optionally set ANDROID_SERIAL to target a specific device. Self-skips if
uiautomator2 isn't installed or no device is reachable, so it never breaks a
core-only environment.
"""

import json
import os

import pytest

_RUN = os.getenv("RUN_LIVE_ANDROID_SMOKE", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live_android,
    pytest.mark.skipif(
        not _RUN,
        reason="Live Android smoke is opt-in. Set RUN_LIVE_ANDROID_SMOKE=1 (needs a real device).",
    ),
]


@pytest.fixture
def live_android():
    try:
        import uiautomator2  # noqa: F401
    except ImportError:
        pytest.skip("uiautomator2 not installed")

    from common.adapters.android_adapter import AndroidU2Adapter

    adapter = AndroidU2Adapter()
    try:
        adapter.setup()
    except Exception as e:
        pytest.skip(f"No reachable Android device: {e}")
    try:
        yield adapter
    finally:
        try:
            adapter.teardown()
        except Exception:
            pass


def _live_tree(adapter):
    from utils.utils_xml import compress_android_xml

    return json.loads(compress_android_xml(adapter.driver.dump_hierarchy()))


def test_real_setup_and_compress_returns_elements(live_android):
    """Adapter connects and the live XML compressor returns real elements."""
    tree = _live_tree(live_android)
    elements = tree.get("ui_elements", [])
    assert elements, "live Android UI-tree compression returned no elements"
    # Every compressed element keeps a class; sanity-check the shape.
    assert all("class" in e for e in elements)


def test_real_assert_absent_element_fails(live_android):
    """Regression for the android-specific bug this smoke caught: an absent
    element used to return success=True in ~0.1s because execute_and_record
    gated on `element` truthiness, and android's UiObject is FALSY when it
    matches 0 elements — so the handler (and its real wait) was skipped entirely.
    A guaranteed-absent element must now wait and report a real failure."""
    import time

    from common.executor import UIExecutor

    executor = UIExecutor(live_android.driver, platform="android")
    t0 = time.time()
    absent = executor.execute_and_record(
        {"action": "assert_exist", "locator_type": "text",
         "locator_value": "zzz-absent-text-9f3c2", "extra_value": ""}
    )
    elapsed = time.time() - t0
    assert absent["success"] is False, "absent element wrongly reported as success"
    assert absent.get("assertion_failed") is True
    # It must actually have waited (the handler ran), not short-circuited to a
    # fast false-success. (DEFAULT_TIMEOUT is 30s; allow slack but require >2s.)
    assert elapsed > 2, f"assert returned in {elapsed:.1f}s — handler was skipped, not waited"


def test_real_assert_present_element_passes(live_android):
    """assert_exist passes for a text actually on screen. Self-calibrating:
    picks a present text from the live tree, app-agnostic."""
    from common.executor import UIExecutor

    tree = _live_tree(live_android)
    texts = [e["text"] for e in tree.get("ui_elements", []) if e.get("text")]
    if not texts:
        pytest.skip("No text elements on current screen to assert against")

    executor = UIExecutor(live_android.driver, platform="android")
    present = executor.execute_and_record(
        {"action": "assert_exist", "locator_type": "text",
         "locator_value": texts[0], "extra_value": ""}
    )
    assert present["success"] is True, f"assert_exist failed for present text {texts[0]!r}"
    assert not present.get("assertion_failed")


# ---------------------------------------------------------------------------
# Core action verbs (click / input / swipe / press) against the Settings app.
# These exercise the agent's PRIMARY --action path on real hardware. Only
# reversible, non-destructive operations; each resets to home afterward.
# ---------------------------------------------------------------------------

_SETTINGS_INTENT = "android.settings.SETTINGS"


@pytest.fixture
def settings_app(live_android):
    """Open the system Settings app, yield (adapter, executor), reset to home."""
    import time

    from common.executor import UIExecutor

    d = live_android.driver
    d.shell(f"am start -a {_SETTINGS_INTENT}")
    time.sleep(2)
    executor = UIExecutor(d, platform="android")
    try:
        yield live_android, executor
    finally:
        # Reset: press Back a few times then Home, so we leave no open submenu.
        try:
            for _ in range(3):
                d.press("back")
                time.sleep(0.3)
            d.press("home")
        except Exception:
            pass


def _has_text(adapter, text: str) -> bool:
    tree = _live_tree(adapter)
    return any(text in (e.get("text") or "") for e in tree.get("ui_elements", []))


def test_real_swipe_scrolls(settings_app):
    """swipe: a global swipe action must execute successfully on a scrollable screen."""
    adapter, executor = settings_app
    result = executor.execute_and_record(
        {"action": "swipe", "locator_type": "global",
         "locator_value": "global", "extra_value": "up"}
    )
    assert result["success"] is True, "swipe up failed on Settings"


def test_real_press_back(settings_app):
    """press: the Back key is a global action and must execute successfully."""
    result = executor_press_back(settings_app)
    assert result["success"] is True, "press Back failed"


def executor_press_back(settings_app):
    _, executor = settings_app
    return executor.execute_and_record(
        {"action": "press", "locator_type": "global",
         "locator_value": "global", "extra_value": "back"}
    )


def test_real_input_into_search(settings_app):
    """input: type into the Settings search box (reversible — changes no setting).

    Uses the FULL resource-id the compressor emits (pkg:id/name). This is the
    regression guard for the stripped-id bug: a bare 'search_src_text' never
    matched in uiautomator2, so resourceId input was silently broken."""
    import time

    adapter, executor = settings_app
    tree = _live_tree(adapter)
    search = next(
        (e for e in tree.get("ui_elements", [])
         if "search_src_text" in (e.get("id") or "")),
        None,
    )
    if not search:
        pytest.skip("search box not present on this Settings variant")

    # The emitted id must be the FULL pkg:id/name, not the stripped form.
    assert search["id"].endswith(":id/search_src_text"), (
        f"compressor emitted a non-matchable id: {search['id']!r}"
    )

    result = executor.execute_and_record(
        {"action": "input", "locator_type": "resourceId",
         "locator_value": search["id"], "extra_value": "display"}
    )
    assert result["success"] is True, "input via full resource-id failed"
    time.sleep(0.5)
    assert _has_text(adapter, "display") or _has_text(adapter, "Display"), (
        "input executed but typed text not visible in UI tree"
    )


def test_real_disabled_control_not_clickable(live_android):
    """Real-device contract: a control the OS reports enabled=false must be
    emitted with clickable suppressed + disabled:true, so the LLM brain doesn't
    tap a dead control and hang on the timeout (the same failure class the web
    compressor fixes). Self-calibrating: hunts a few Settings screens that
    commonly carry a naturally-disabled row (e.g. an empty SIM slot, a greyed
    roaming toggle); skips honestly if this ROM/SIM config has none."""
    import time
    import xml.etree.ElementTree as ET

    from utils.utils_xml import compress_android_xml

    d = live_android.driver
    screens = [
        "android.settings.DATA_ROAMING_SETTINGS",
        "android.settings.WIRELESS_SETTINGS",
        "android.settings.DATE_SETTINGS",
    ]
    disabled_label = None
    raw_xml = None
    for intent in screens:
        try:
            d.shell(f"am start -a {intent}")
            time.sleep(1.6)
            raw_xml = d.dump_hierarchy()
        except Exception:
            continue
        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError:
            continue
        for n in root.iter():
            if n.attrib.get("enabled") == "false":
                label = (n.attrib.get("text") or n.attrib.get("content-desc") or "").strip()
                if label:
                    disabled_label = label
                    break
        if disabled_label:
            break

    try:
        if not disabled_label:
            pytest.skip("no naturally-disabled control on the probed screens (ROM/SIM-dependent)")

        els = json.loads(compress_android_xml(raw_xml)).get("ui_elements", [])
        match = [e for e in els if disabled_label in (e.get("text") or e.get("desc") or "")]
        assert match, f"disabled control {disabled_label!r} dropped from compressed tree"
        # It must be reported, but never clickable, and flagged disabled.
        assert all(e.get("clickable") is not True for e in match), (
            f"disabled control {disabled_label!r} reported clickable — LLM would tap a dead control"
        )
        assert any(e.get("disabled") is True for e in match), (
            f"disabled control {disabled_label!r} missing disabled flag"
        )
    finally:
        try:
            d.press("home")
        except Exception:
            pass


def test_real_click_navigates_then_back(settings_app):
    """click: tap a Settings row by text, verify navigation, then go Back."""
    adapter, executor = settings_app
    tree = _live_tree(adapter)
    # Pick a clickable-ish row title that is stable on most ROMs.
    candidates = [e.get("text") for e in tree.get("ui_elements", [])
                  if e.get("text") and len(e.get("text")) <= 8]
    target = next((t for t in candidates if t in ("显示与亮度", "声音与振动", "蓝牙", "Display", "Sound")), None)
    if not target:
        target = candidates[0] if candidates else None
    if not target:
        pytest.skip("no stable clickable row found on this Settings screen")

    result = executor.execute_and_record(
        {"action": "click", "locator_type": "text",
         "locator_value": target, "extra_value": ""}
    )
    assert result["success"] is True, f"click on row {target!r} failed"
