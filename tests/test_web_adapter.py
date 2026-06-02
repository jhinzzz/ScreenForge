"""Tests for common/adapters/web_adapter.py — recording wiring (audit T2).

Regression guard: the persistent-browser refactor created the context with
new_context(viewport=...) but never passed record_video_dir, while
stop_record_and_get_path() called self.driver.video.path() — which is None
when recording was never enabled, so web recording silently produced nothing
(or raised, caught as "video file not found").

These tests pin the contract:
- a freshly created context gets record_video_dir / record_video_size
- a reused context does NOT (Playwright can't enable recording after creation)
- stop_record_and_get_path() returns "" cleanly when recording was never on,
  instead of touching driver.video
"""

from unittest.mock import MagicMock

from common.adapters.web_adapter import WebPlaywrightAdapter


def _make_adapter():
    adapter = WebPlaywrightAdapter()
    # avoid touching the real filesystem state file
    adapter.state_file = "/nonexistent/never/browser_state.json"
    return adapter


def test_new_context_enables_recording_with_video_dir():
    adapter = _make_adapter()
    browser = MagicMock()
    browser.contexts = []  # force the "create new context" branch
    new_context = MagicMock()
    browser.new_context.return_value = new_context
    adapter.browser = browser

    adapter._create_context_and_page()

    # new_context must receive recording params
    _, kwargs = browser.new_context.call_args
    assert kwargs.get("record_video_dir") == adapter.video_dir
    assert kwargs.get("record_video_size") == adapter.video_size
    assert adapter._recording_enabled is True
    new_context.new_page.assert_called_once()


def test_reused_context_disables_recording():
    adapter = _make_adapter()
    browser = MagicMock()
    existing_context = MagicMock()
    browser.contexts = [existing_context]  # force the "reuse" branch
    adapter.browser = browser

    adapter._create_context_and_page()

    # must NOT create a new context, and recording stays off
    browser.new_context.assert_not_called()
    assert adapter._recording_enabled is False
    existing_context.new_page.assert_called_once()


def test_stop_record_skips_cleanly_when_recording_disabled():
    adapter = _make_adapter()
    adapter._recording_enabled = False
    # driver.video access would blow up if reached — make it explode to prove
    # we never touch it on the disabled path.
    driver = MagicMock()
    type(driver).video = property(
        lambda self: (_ for _ in ()).throw(AssertionError("video must not be accessed"))
    )
    adapter.driver = driver
    adapter.context = MagicMock()

    assert adapter.stop_record_and_get_path("out.webm") == ""


def test_stop_record_handles_none_video_when_enabled():
    adapter = _make_adapter()
    adapter._recording_enabled = True
    driver = MagicMock()
    driver.video = None  # page without an attached video object
    adapter.driver = driver
    adapter.context = MagicMock()

    # should warn and return "" rather than raising on None.path()
    assert adapter.stop_record_and_get_path("out.webm") == ""
