"""Live Android smoke test — real device via uiautomator2, no mocks.

Same rationale as tests/test_web_smoke_live.py: prove the audit-touched Android
paths work on real hardware, not just under mocks. Drives a real device through
adapter setup → live UI-tree capture/compression → the executor assert pass/fail
contract.

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
