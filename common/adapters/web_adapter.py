import json
import os
import subprocess
import sys
import time

import config.config as config
from common.logs import log

from .base_adapter import BasePlatformAdapter

_SESSION_FILE = os.path.abspath(os.path.join("report", "web_session.json"))
_CDP_PORT = 9333


def _read_session() -> dict | None:
    if not os.path.exists(_SESSION_FILE):
        return None
    try:
        with open(_SESSION_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _write_session(cdp_url: str, pid: int) -> None:
    os.makedirs(os.path.dirname(_SESSION_FILE), exist_ok=True)
    with open(_SESSION_FILE, "w") as f:
        json.dump({"cdp_url": cdp_url, "pid": pid}, f)


def _clear_session() -> None:
    if os.path.exists(_SESSION_FILE):
        os.remove(_SESSION_FILE)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def stop_persistent_browser() -> bool:
    """Terminate the detached persistent Chromium recorded in the session file.

    The web adapter launches Chromium with --remote-debugging-port and keeps it
    running across CLI calls (teardown only disconnects). Nothing else ever kills
    it, so repeated runs leak browsers holding port 9333. This is the explicit
    reaper, wired to `--web-stop`. Returns True if a live process was signalled.
    """
    import signal

    session = _read_session()
    if not session:
        log.info("ℹ️ [System] No persistent web browser session on record")
        return False

    pid = session.get("pid", 0)
    if not pid or not _is_process_alive(pid):
        log.info("ℹ️ [System] Recorded browser is not running; clearing stale session")
        _clear_session()
        return False

    try:
        if sys.platform == "win32":
            import subprocess as _sp
            _sp.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        log.info(f"✅ [System] Stopped persistent Chromium (pid {pid})")
        _clear_session()
        return True
    except Exception as e:
        log.error(f"❌ [Error] Failed to stop persistent browser (pid {pid}): {e}")
        return False


class WebPlaywrightAdapter(BasePlatformAdapter):

    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.context = None
        self.driver = None
        self._chromium_process = None

        self.state_file = os.path.abspath(os.path.join("report", "browser_state.json"))
        self.viewport_size = {"width": 1920, "height": 1080}

    def setup(self):
        log.info("⏱️ [System] Initializing Web (Playwright) browser...")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("❌ [Error] playwright not installed. Run: pip install playwright && playwright install")
            raise

        self.playwright = sync_playwright().start()

        if self._try_reconnect():
            return

        self._launch_persistent_browser()

    def _try_reconnect(self) -> bool:
        session = _read_session()
        if not session:
            return False

        cdp_url = session.get("cdp_url", "")
        pid = session.get("pid", 0)

        if not cdp_url or not _is_process_alive(pid):
            log.info("⚠️ [System] Persistent browser no longer exists, launching new one")
            _clear_session()
            return False

        try:
            self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
            log.info("✅ [System] Reconnected to persistent browser session")

            if self.browser.contexts:
                self.context = self.browser.contexts[0]
                if self.context.pages:
                    self.driver = self.context.pages[0]
                    self.driver.set_default_timeout(config.DEFAULT_TIMEOUT * 1000)
                    log.info(f"✅ [System] Reusing existing page: {self.driver.url}")
                    return True

            self._create_context_and_page()
            return True

        except Exception as e:
            log.info(f"⚠️ [System] Reconnect failed ({e}), launching new browser")
            _clear_session()
            return False

    def _launch_persistent_browser(self):
        chromium_path = self.playwright.chromium.executable_path
        if not chromium_path or not os.path.exists(chromium_path):
            log.error("❌ [Error] Playwright Chromium not found. Run: playwright install chromium")
            raise RuntimeError("Playwright Chromium not found")

        cdp_url = f"http://127.0.0.1:{_CDP_PORT}"
        user_data_dir = os.path.abspath(os.path.join("report", "chromium_profile"))
        os.makedirs(user_data_dir, exist_ok=True)

        log.info(f"🚀 [System] Launching persistent Chromium (CDP: {cdp_url})...")
        self._chromium_process = subprocess.Popen(
            [
                chromium_path,
                f"--remote-debugging-port={_CDP_PORT}",
                f"--user-data-dir={user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                f"--window-size={self.viewport_size['width']},{self.viewport_size['height']}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(30):
            try:
                import urllib.request
                urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"Chromium CDP port {_CDP_PORT} startup timed out")

        _write_session(cdp_url, self._chromium_process.pid)

        self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
        log.info("✅ [System] Persistent Chromium launched and connected")

        if self.browser.contexts and self.browser.contexts[0].pages:
            self.context = self.browser.contexts[0]
            self.driver = self.context.pages[0]
            self.driver.set_default_timeout(config.DEFAULT_TIMEOUT * 1000)
        else:
            self._create_context_and_page()

    def _create_context_and_page(self):
        # NOTE: no video recording here. The adapter attaches to Chromium over CDP
        # (connect_over_cdp) for cross-call session reuse, and Playwright cannot
        # record video for a CDP-attached browser — `page.video` yields an object
        # but no file is ever written. Recording only works for a browser
        # Playwright launches itself, which this design does not do. Web video is
        # therefore unsupported; see stop_record_and_get_path().
        if self.browser.contexts:
            self.context = self.browser.contexts[0]
        else:
            self.context = self.browser.new_context(viewport=self.viewport_size)

        if os.path.exists(self.state_file):
            try:
                import json as _json
                with open(self.state_file, "r") as f:
                    state = _json.load(f)
                for cookie in state.get("cookies", []):
                    self.context.add_cookies([cookie])
                log.info(f"✅ [System] Restored browser state from: {self.state_file}")
            except Exception as e:
                log.warning(f"⚠️ [Warning] Failed to restore browser state: {e}")

        self.driver = self.context.new_page()
        self.driver.set_default_timeout(config.DEFAULT_TIMEOUT * 1000)

    def teardown(self):
        log.info("⏱️ [System] Saving state and disconnecting (browser keeps running)...")
        try:
            if self.context:
                try:
                    os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                    self.context.storage_state(path=self.state_file)
                    log.info(f"✅ [System] Browser state saved to: {self.state_file}")
                except Exception as e:
                    log.warning(f"⚠️ [Warning] Failed to save browser state: {e}")
        finally:
            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception:
                    pass

    def start_record(self, video_name: str):
        # Web video recording is unsupported (CDP-attached browser; see
        # _create_context_and_page). No-op kept for the adapter interface.
        log.info("ℹ️ [System] Web video recording is not supported (CDP session)")

    def stop_record_and_get_path(self, video_name: str) -> str:
        # Unsupported on web — return "" cleanly. (This also avoids the old
        # AttributeError: stop used to call self.driver.video.path() which is
        # None when no record_video_dir was set.)
        return ""

    def take_screenshot(self) -> bytes:
        if self.driver:
            return self.driver.screenshot()
        return b""
