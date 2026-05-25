import io
import os
import signal
import subprocess
import sys
import time

import config.config as config
from common.logs import log

from .base_adapter import BasePlatformAdapter

_SESSION_FILE = os.path.abspath(os.path.join("report", "ios_session.json"))


def _read_session() -> dict | None:
    if not os.path.exists(_SESSION_FILE):
        return None
    try:
        import json
        with open(_SESSION_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _write_session(wda_url: str, udid: str) -> None:
    import json
    os.makedirs(os.path.dirname(_SESSION_FILE), exist_ok=True)
    with open(_SESSION_FILE, "w") as f:
        json.dump({"wda_url": wda_url, "udid": udid}, f)


def _clear_session() -> None:
    if os.path.exists(_SESSION_FILE):
        os.remove(_SESSION_FILE)


def _is_wda_alive(url: str, timeout: float = 3.0) -> bool:
    try:
        import urllib.request
        urllib.request.urlopen(f"{url}/status", timeout=timeout)
        return True
    except Exception:
        return False


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _find_device_udid() -> str:
    if config.IOS_DEVICE_UDID:
        return config.IOS_DEVICE_UDID
    if not _is_macos():
        return ""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            for runtime_devices in data.get("devices", {}).values():
                for device in runtime_devices:
                    if device.get("state") == "Booted":
                        return device.get("udid", "")
    except Exception:
        pass
    return ""


class IosWdaAdapter(BasePlatformAdapter):

    def __init__(self):
        super().__init__()
        self._wda_url = config.WDA_URL
        self._udid = ""
        self._record_process = None
        self._record_path = ""

    def setup(self):
        log.info("⏳ [Setup] Initializing iOS (WDA) device...")

        try:
            import wda
        except ImportError:
            log.error(
                "❌ [E040] facebook-wda not installed. "
                "Fix: pip install screenforge[ios] or pip install facebook-wda"
            )
            raise RuntimeError(
                "facebook-wda not installed. Run: pip install screenforge[ios]"
            )

        if self._try_reconnect(wda):
            return

        self._connect_fresh(wda)

    def _try_reconnect(self, wda_module) -> bool:
        session = _read_session()
        if not session:
            return False

        url = session.get("wda_url", "")
        if not url or not _is_wda_alive(url):
            log.info("⚠️ [System] Previous WDA session no longer alive, connecting fresh")
            _clear_session()
            return False

        try:
            self.driver = wda_module.Client(url)
            self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)
            status = self.driver.status()
            log.info(
                f"✅ [System] Reconnected to WDA session "
                f"(iOS {status.get('os', {}).get('version', 'unknown')})"
            )
            self._wda_url = url
            self._udid = session.get("udid", "")
            return True
        except Exception as e:
            log.info(f"⚠️ [System] Reconnect failed ({e}), connecting fresh")
            _clear_session()
            return False

    def _connect_fresh(self, wda_module):
        if not _is_wda_alive(self._wda_url):
            log.error(
                f"❌ [E041] WebDriverAgent not reachable at {self._wda_url}. "
                "Fix: start WDA on the device first. "
                "See: https://github.com/appium/WebDriverAgent"
            )
            raise RuntimeError(
                f"WebDriverAgent not reachable at {self._wda_url}. "
                "Ensure WDA is running on the target device."
            )

        try:
            self.driver = wda_module.Client(self._wda_url)
            self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)
            status = self.driver.status()
            self._udid = _find_device_udid()
            _write_session(self._wda_url, self._udid)
            log.info(
                f"✅ [System] Connected to iOS device via WDA "
                f"(iOS {status.get('os', {}).get('version', 'unknown')}, "
                f"UDID: {self._udid or 'auto'})"
            )
        except Exception as e:
            log.error(f"❌ [E042] Failed to connect to WDA at {self._wda_url}: {e}")
            raise RuntimeError(f"WDA connection failed: {e}")

    def teardown(self):
        log.info("⏳ [Teardown] Disconnecting iOS device...")
        if self._record_process:
            self.stop_record_and_get_path("")
        if self.driver:
            try:
                self.driver.session().close()
            except Exception:
                pass
            self.driver = None
        log.info("✅ [System] iOS device disconnected")

    def start_record(self, video_name: str):
        if not _is_macos():
            log.info(
                "⚠️ [System] iOS recording requires macOS with Xcode. "
                "Skipping on this platform."
            )
            return

        udid = self._udid or _find_device_udid()
        if not udid:
            log.warning(
                "⚠️ [Warning] Cannot determine device UDID for recording. "
                "Fix: export IOS_DEVICE_UDID=<your-udid> or boot a simulator"
            )
            return

        video_dir = os.path.abspath("report")
        os.makedirs(video_dir, exist_ok=True)
        if not video_name.endswith(".mov"):
            video_name = video_name + ".mov"
        self._record_path = os.path.join(video_dir, video_name)

        log.info(f"📹 [System] Starting iOS screen recording (UDID: {udid})...")
        try:
            cmd = ["xcrun", "simctl", "io", udid, "recordVideo", self._record_path]
            self._record_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
            )
            time.sleep(1.0)
            if self._record_process.poll() is not None:
                stderr = self._record_process.stderr.read().decode() if self._record_process.stderr else ""
                log.error(f"❌ [Error] xcrun simctl recordVideo crashed on startup: {stderr}")
                self._record_process = None
        except FileNotFoundError:
            log.error(
                "❌ [Error] xcrun not found. "
                "Fix: install Xcode Command Line Tools (xcode-select --install)"
            )
        except Exception as e:
            log.error(f"❌ [Error] Failed to start iOS recording: {e}")

    def stop_record_and_get_path(self, video_name: str = "") -> str:
        if not self._record_process:
            return ""

        log.info("⏳ [System] Stopping iOS recording...")
        try:
            pgid = os.getpgid(self._record_process.pid)
            os.killpg(pgid, signal.SIGINT)
            self._record_process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            log.warning("[Warning] Recording did not stop in time, force killing...")
            try:
                pgid = os.getpgid(self._record_process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                self._record_process.kill()
            self._record_process.wait()
        except OSError:
            try:
                self._record_process.send_signal(signal.SIGINT)
                self._record_process.wait(timeout=2)
            except Exception:
                self._record_process.kill()
                self._record_process.wait()
        except Exception as e:
            log.error(f"❌ [Error] Failed to stop recording: {e}")

        self._record_process = None

        actual_path = getattr(self, "_record_path", "")
        if actual_path and os.path.exists(actual_path):
            file_size = os.path.getsize(actual_path)
            if file_size < 1024:
                log.warning(f"⚠️ [Warning] Recording file size abnormal: {file_size} bytes")
            else:
                log.info(f"✅ [System] iOS recording saved ({file_size // 1024} KB)")
            return actual_path

        return ""

    def take_screenshot(self, _retry: bool = True) -> bytes:
        if not self.driver:
            log.error("❌ [E043] Cannot take screenshot: no WDA connection")
            return b""
        try:
            image = self.driver.screenshot()
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            return img_bytes.getvalue()
        except Exception as e:
            log.error(f"❌ [E044] Screenshot failed: {e}")
            if _retry and self._attempt_reconnect():
                return self.take_screenshot(_retry=False)
            return b""

    def _attempt_reconnect(self) -> bool:
        log.info("⚠️ [System] Attempting WDA reconnect...")
        try:
            import wda
            if _is_wda_alive(self._wda_url):
                self.driver = wda.Client(self._wda_url)
                self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)
                log.info("✅ [System] WDA reconnected successfully")
                return True
        except Exception as e:
            log.error(f"❌ [System] Reconnect failed: {e}")
        return False
