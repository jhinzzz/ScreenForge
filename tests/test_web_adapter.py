"""Tests for common/adapters/web_adapter.py.

Web video recording is UNSUPPORTED: the adapter attaches to Chromium over CDP
(connect_over_cdp) for cross-call session reuse, and Playwright cannot record
video for a CDP-attached browser (verified on real hardware — page.video yields
an object but no file is ever written). So the contract here is:
  - _create_context_and_page never passes record_video_dir
  - stop_record_and_get_path returns "" cleanly, WITHOUT touching driver.video
    (the original bug was an AttributeError from driver.video.path() being None)

Plus the --web-stop reaper (T9) for the leaked persistent Chromium.
"""

from unittest.mock import MagicMock

import common.adapters.web_adapter as web_adapter
from common.adapters.web_adapter import WebPlaywrightAdapter, stop_persistent_browser


def _make_adapter():
    adapter = WebPlaywrightAdapter()
    # avoid touching the real filesystem state file
    adapter.state_file = "/nonexistent/never/browser_state.json"
    return adapter


def test_new_context_does_not_request_recording():
    # CDP can't record; we must NOT pass record_video_dir (it would be a silent
    # no-op that misleads callers into expecting a video).
    adapter = _make_adapter()
    browser = MagicMock()
    browser.contexts = []  # force the "create new context" branch
    browser.new_context.return_value = MagicMock()
    adapter.browser = browser

    adapter._create_context_and_page()

    _, kwargs = browser.new_context.call_args
    assert "record_video_dir" not in kwargs
    assert "record_video_size" not in kwargs


def test_reused_context_creates_no_new_context():
    adapter = _make_adapter()
    browser = MagicMock()
    existing = MagicMock()
    browser.contexts = [existing]  # reuse branch
    adapter.browser = browser

    adapter._create_context_and_page()

    browser.new_context.assert_not_called()
    existing.new_page.assert_called_once()


def test_stop_record_returns_empty_without_touching_driver_video():
    # Regression: stop used to call self.driver.video.path() -> AttributeError
    # when no record_video_dir was set. It must now short-circuit cleanly.
    adapter = _make_adapter()
    driver = MagicMock()
    type(driver).video = property(
        lambda self: (_ for _ in ()).throw(AssertionError("video must not be accessed"))
    )
    adapter.driver = driver
    adapter.context = MagicMock()

    assert adapter.stop_record_and_get_path("out.webm") == ""


def test_start_record_is_noop():
    adapter = _make_adapter()
    # Must not raise; recording is unsupported on web.
    adapter.start_record("whatever.webm")


class TestStopPersistentBrowser:
    """--web-stop reaper (T9): kill the leaked detached Chromium."""

    def test_no_session_returns_false(self, monkeypatch):
        monkeypatch.setattr(web_adapter, "_read_session", lambda: None)
        assert stop_persistent_browser() is False

    def test_dead_pid_clears_stale_session(self, monkeypatch):
        cleared = {"done": False}
        monkeypatch.setattr(web_adapter, "_read_session", lambda: {"pid": 4242})
        monkeypatch.setattr(web_adapter, "_is_process_alive", lambda pid: False)
        monkeypatch.setattr(web_adapter, "_clear_session", lambda: cleared.update(done=True))
        assert stop_persistent_browser() is False
        assert cleared["done"] is True

    def test_live_pid_is_signalled_and_cleared(self, monkeypatch):
        killed = {}
        cleared = {"done": False}
        monkeypatch.setattr(web_adapter, "_read_session", lambda: {"pid": 4242})
        monkeypatch.setattr(web_adapter, "_is_process_alive", lambda pid: True)
        monkeypatch.setattr(web_adapter, "_clear_session", lambda: cleared.update(done=True))
        monkeypatch.setattr(web_adapter.sys, "platform", "darwin")
        monkeypatch.setattr(web_adapter.os, "kill", lambda pid, sig: killed.update(pid=pid, sig=sig))

        assert stop_persistent_browser() is True
        assert killed["pid"] == 4242
        import signal
        assert killed["sig"] == signal.SIGTERM
        assert cleared["done"] is True
