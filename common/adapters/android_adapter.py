import io
import json
import os
import signal
import subprocess
import sys
import time

import config.config as config
from common.logs import log

from .base_adapter import BasePlatformAdapter

_SESSION_FILE = os.path.abspath(os.path.join("report", "android_session.json"))


def _read_session() -> dict | None:
    if not os.path.exists(_SESSION_FILE):
        return None
    try:
        with open(_SESSION_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _write_session(serial: str) -> None:
    os.makedirs(os.path.dirname(_SESSION_FILE), exist_ok=True)
    with open(_SESSION_FILE, "w") as f:
        json.dump({"serial": serial, "ts": time.time()}, f)


def _clear_session() -> None:
    if os.path.exists(_SESSION_FILE):
        os.remove(_SESSION_FILE)


def _is_device_online(serial: str) -> bool:
    try:
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                if not serial or parts[0] == serial:
                    return True
        return False
    except Exception:
        return False


class AndroidU2Adapter(BasePlatformAdapter):

    def __init__(self):
        super().__init__()
        self._serial = config.ANDROID_SERIAL
        self._scrcpy_process = None

    def setup(self):
        log.info("⏳ [Setup] Initializing Android (u2) device...")

        try:
            import uiautomator2 as u2
        except ImportError:
            log.error(
                "❌ [E050] uiautomator2 not installed. "
                "Fix: pip install screenforge[android] or pip install uiautomator2"
            )
            raise RuntimeError(
                "uiautomator2 not installed. Run: pip install screenforge[android]"
            )

        if self._try_reconnect(u2):
            return

        self._connect_fresh(u2)

    def _try_reconnect(self, u2_module) -> bool:
        session = _read_session()
        if not session:
            return False

        serial = session.get("serial", "")
        if not serial or not _is_device_online(serial):
            log.info("⚠️ [System] Previous Android session device offline, connecting fresh")
            _clear_session()
            return False

        try:
            self.driver = u2_module.connect(serial)
            self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)
            info = self.driver.info
            log.info(
                f"✅ [System] Reconnected to Android device "
                f"({info.get('productName', 'unknown')}, serial: {serial})"
            )
            self._serial = serial
            return True
        except Exception as e:
            log.info(f"⚠️ [System] Reconnect failed ({e}), connecting fresh")
            _clear_session()
            return False

    def _connect_fresh(self, u2_module):
        serial = self._serial

        if serial and not _is_device_online(serial):
            log.error(
                f"❌ [E051] Android device '{serial}' not found or offline. "
                "Fix: check 'adb devices' output and ensure the device is connected"
            )
            raise RuntimeError(
                f"Android device '{serial}' not found. Run 'adb devices' to verify."
            )

        if not serial and not _is_device_online(""):
            log.error(
                "❌ [E052] No Android device connected. "
                "Fix: connect a device via USB or start an emulator, then run 'adb devices'"
            )
            raise RuntimeError(
                "No Android device connected. Run 'adb devices' to verify."
            )

        try:
            connect_arg = serial if serial else None
            self.driver = u2_module.connect(connect_arg)
            self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)
            self._serial = self.driver.serial
            _write_session(self._serial)

            info = self.driver.info
            log.info(
                f"✅ [System] Connected to Android device "
                f"({info.get('productName', 'unknown')}, "
                f"SDK: {info.get('sdkInt', '?')}, serial: {self._serial})"
            )
        except Exception as e:
            log.error(f"❌ [E053] Failed to connect to Android device: {e}")
            raise RuntimeError(f"Android device connection failed: {e}")

    def teardown(self):
        log.info("⏳ [Teardown] Disconnecting Android device...")
        if self._scrcpy_process:
            self.stop_record_and_get_path("")
        if self.driver:
            try:
                self.driver.service("uiautomator").stop()
            except Exception:
                pass
            self.driver = None
        log.info("✅ [System] Android device disconnected")

    def start_record(self, video_name: str):
        log.info("📹 [System] Starting scrcpy recording...")
        try:
            serial = self._serial or (self.driver.serial if self.driver else "")
            if not serial:
                log.warning("⚠️ [Warning] Cannot determine device serial for recording")
                return

            cmd = [
                "scrcpy",
                "-s", serial,
                "--no-playback",
                "--record", video_name,
                "--video-bit-rate", "2M",
                "--max-fps", "30",
            ]

            popen_kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["preexec_fn"] = os.setsid

            self._scrcpy_process = subprocess.Popen(cmd, **popen_kwargs)
            time.sleep(1.0)

            if self._scrcpy_process.poll() is not None:
                log.error("❌ [Error] scrcpy crashed on startup")
                self._scrcpy_process = None

        except FileNotFoundError:
            log.error(
                "❌ [Error] scrcpy not found in PATH. "
                "Fix: brew install scrcpy (macOS) or see https://github.com/Genymobile/scrcpy"
            )
        except Exception as e:
            log.error(f"❌ [Error] Failed to start scrcpy: {e}")

    def stop_record_and_get_path(self, video_name: str) -> str:
        if not self._scrcpy_process:
            return ""

        log.info("⏳ [System] Stopping scrcpy recording...")
        try:
            if sys.platform == "win32":
                self._scrcpy_process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                pgid = os.getpgid(self._scrcpy_process.pid)
                os.killpg(pgid, signal.SIGINT)
            self._scrcpy_process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            log.warning("[Warning] scrcpy did not exit in time, force killing...")
            try:
                if sys.platform == "win32":
                    self._scrcpy_process.kill()
                else:
                    pgid = os.getpgid(self._scrcpy_process.pid)
                    os.killpg(pgid, signal.SIGKILL)
            except Exception:
                self._scrcpy_process.kill()
            self._scrcpy_process.wait()
        except OSError:
            try:
                self._scrcpy_process.send_signal(signal.SIGINT)
                self._scrcpy_process.wait(timeout=2)
            except Exception:
                self._scrcpy_process.kill()
                self._scrcpy_process.wait()
        except Exception as e:
            log.error(f"❌ [Error] Failed to stop scrcpy: {e}")

        self._scrcpy_process = None
        return self._validate_video_file(video_name)

    def take_screenshot(self, _retry: bool = True) -> bytes:
        if not self.driver:
            log.error("❌ [E054] Cannot take screenshot: no device connection")
            return b""
        try:
            image = self.driver.screenshot()
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            return img_bytes.getvalue()
        except Exception as e:
            log.error(f"❌ [E055] Screenshot failed: {e}")
            if _retry and self._attempt_reconnect():
                return self.take_screenshot(_retry=False)
            return b""

    def _attempt_reconnect(self) -> bool:
        log.info("⚠️ [System] Attempting Android device reconnect...")
        try:
            import uiautomator2 as u2
            if _is_device_online(self._serial):
                connect_arg = self._serial if self._serial else None
                self.driver = u2.connect(connect_arg)
                self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)
                log.info("✅ [System] Android device reconnected successfully")
                return True
        except Exception as e:
            log.error(f"❌ [System] Reconnect failed: {e}")
        return False

    def _validate_video_file(self, video_name: str) -> str:
        if not video_name:
            return ""
        if os.path.exists(video_name):
            file_size = os.path.getsize(video_name)
            if file_size < 1024:
                log.warning(f"⚠️ [Warning] Recording file size abnormal: {file_size} bytes")
            else:
                log.info(f"✅ [System] Recording saved ({file_size // 1024} KB)")
            return video_name
        else:
            log.error(f"❌ [Error] Recording file not found: {video_name}")
            return ""
