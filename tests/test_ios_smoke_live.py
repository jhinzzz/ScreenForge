"""Live iOS smoke test — real booted simulator.

Scope note: the iOS *adapter* (facebook-wda) needs WebDriverAgent running on the
device, which is not auto-installed on a stock simulator — those checks self-skip
when WDA is unreachable. What DOES run on a bare booted sim (only `simctl`) is the
session-recording reaper in cli/session.py, which is structurally the same
"detached process, killed cross-process by PID" shape as the web --web-stop bug.
A real-hardware probe during the audit showed this path actually reaps cleanly
(SIGINT is simctl's correct stop signal and the recorder reparents to launchd),
so this guards that it stays correct.

OPT-IN: skipped by default. Enable with a booted simulator (macOS):

    RUN_LIVE_IOS_SMOKE=1 pytest tests/test_ios_smoke_live.py -v
"""

import json
import os
import subprocess
import sys
import time

import pytest

_RUN = os.getenv("RUN_LIVE_IOS_SMOKE", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live_ios,
    pytest.mark.skipif(
        not _RUN,
        reason="Live iOS smoke is opt-in. Set RUN_LIVE_IOS_SMOKE=1 (needs a booted simulator).",
    ),
]


def _booted_udid() -> str:
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted", "-j"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        for devices in data.get("devices", {}).values():
            for dev in devices:
                if dev.get("state") == "Booted":
                    return dev.get("udid", "")
    except Exception:
        return ""
    return ""


@pytest.fixture
def booted_sim():
    if sys.platform != "darwin":
        pytest.skip("iOS simulators require macOS")
    udid = _booted_udid()
    if not udid:
        pytest.skip("No booted iOS simulator (boot one: xcrun simctl boot <udid>)")
    return udid


def test_session_recording_reaper_no_leak(booted_sim):
    """cli/session.py records via `simctl io recordVideo` (detached, killed by
    PID) — the web-bug shape. Verify start→stop produces a video and leaves no
    surviving/zombie process."""
    import cli.session as session

    sid = "live_ios_smoke"
    session.create_session(sid, "ios", "report/sessions/live_ios_smoke.py")
    try:
        video_path = session.start_session_recording(sid, "ios", udid=booted_sim)
        if not video_path:
            pytest.skip("simctl recordVideo did not start (codec/permission?)")

        pid = session.load_session(sid).get("recording_pid")
        assert pid, "recording started but no pid recorded"
        time.sleep(1.5)

        out = session.stop_session_recording(sid)
        time.sleep(1.0)

        # Process must be fully gone — not alive, not a lingering zombie.
        state = subprocess.run(
            ["ps", "-o", "state=", "-p", str(pid)],
            capture_output=True, text=True,
        ).stdout.strip()
        assert state == "" or state.startswith("Z") is False, (
            f"recorder pid {pid} left in state {state!r} after stop (leak/zombie)"
        )
        assert not state, f"recorder pid {pid} still in process table ({state!r}) after stop"
        # stop returns the video path when the file is non-trivial; tolerate
        # empty (very short clip) but the process-reaping assertion above is the
        # real contract.
        if out:
            assert os.path.exists(out)
    finally:
        session.delete_session(sid)
        try:
            os.remove(f"report/session_{sid}.mov")
        except OSError:
            pass


def test_ios_adapter_requires_wda(booted_sim):
    """The iOS adapter needs WDA; document/verify the skip path when it's absent
    so the suite is honest about what it did and didn't exercise."""
    try:
        import wda  # noqa: F401
    except ImportError:
        pytest.skip("facebook-wda not installed")

    import urllib.request

    from common.adapters.ios_adapter import IosWdaAdapter

    try:
        urllib.request.urlopen("http://localhost:8100/status", timeout=2)
    except Exception:
        pytest.skip("WDA not reachable on :8100 — build/run WebDriverAgent to exercise the iOS adapter")

    adapter = IosWdaAdapter()
    adapter.setup()
    try:
        assert adapter.driver is not None
        src = adapter.driver.source()
        assert src, "WDA returned empty source"
    finally:
        adapter.teardown()


def _wda_reachable() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8100/status", timeout=2)
        return True
    except Exception:
        return False


@pytest.fixture
def wda_adapter():
    """Connected iOS adapter, or skip if WDA isn't running on :8100."""
    try:
        import wda  # noqa: F401
    except ImportError:
        pytest.skip("facebook-wda not installed")
    if sys.platform != "darwin":
        pytest.skip("iOS requires macOS")
    if not _wda_reachable():
        pytest.skip("WDA not reachable on :8100 — start WebDriverAgent to exercise the iOS adapter")

    from common.adapters.ios_adapter import IosWdaAdapter

    adapter = IosWdaAdapter()
    adapter.setup()
    try:
        yield adapter
    finally:
        try:
            adapter.teardown()
        except Exception:
            pass


def _ios_tree(adapter):
    from utils.utils_ios import compress_ios_xml
    return json.loads(compress_ios_xml(adapter.driver.source()))


def test_ios_assert_contract(wda_adapter):
    """T4 on real iOS: assert_exist passes for an on-screen label and fails
    (assertion_failed) for a guaranteed-absent one. Self-calibrating."""
    from common.executor import UIExecutor

    tree = _ios_tree(wda_adapter)
    # Pick a real, interactable element — NOT the app-root containers
    # (Application/Window), whose label is matched by `name`, not `label`, in
    # WDA. A real agent targets controls (buttons, cells, static text), which
    # the executor's text->label mapping resolves correctly.
    _CONTAINER_TYPES = {"Application", "Window", "Other"}
    labels = [
        e["label"] for e in tree.get("ui_elements", [])
        if e.get("label") and e.get("type") not in _CONTAINER_TYPES
    ]
    if not labels:
        pytest.skip("no labeled control elements on current iOS screen")

    executor = UIExecutor(wda_adapter.driver, platform="ios")
    present = executor.execute_and_record(
        {"action": "assert_exist", "locator_type": "text",
         "locator_value": labels[0], "extra_value": ""}
    )
    assert present["success"] is True, f"assert_exist failed for present label {labels[0]!r}"
    assert not present.get("assertion_failed")

    absent = executor.execute_and_record(
        {"action": "assert_exist", "locator_type": "text",
         "locator_value": "zzz-absent-ios-9f3c2", "extra_value": ""}
    )
    assert absent["success"] is False
    assert absent.get("assertion_failed") is True


def test_ios_swipe_all_directions(wda_adapter):
    """Regression for the iOS swipe bug: SwipeHandler used to call swipe_ext()
    (Android-only) on iOS, crashing with AttributeError. All four directions
    must execute via facebook-wda's directional swipe."""
    from common.executor import UIExecutor

    executor = UIExecutor(wda_adapter.driver, platform="ios")
    for direction in ("up", "down", "left", "right"):
        result = executor.execute_and_record(
            {"action": "swipe", "locator_type": "global",
             "locator_value": "global", "extra_value": direction}
        )
        assert result["success"] is True, f"iOS swipe {direction} failed"
        assert f"d.swipe_{direction}()" in "".join(result["code_lines"])
