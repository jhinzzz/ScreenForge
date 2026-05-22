import io
import os
import signal
import subprocess
import sys
import time

import config.config as config
from common.logs import log

from .base_adapter import BasePlatformAdapter


class AndroidU2Adapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__()
        self._scrcpy_process = None

    def setup(self):
        import uiautomator2 as u2
        log.info("⏳ [Setup] Initializing Android (u2) device...")
        self.driver = u2.connect()
        self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)

    def teardown(self):
        log.info("⏳ [Teardown] Disconnecting Android (u2) device...")

    def start_record(self, video_name: str):
        log.info("⏳ [Setup] 📹 Starting scrcpy recording engine...")
        try:
            serial = self.driver.serial
            cmd = [
                "scrcpy",
                "-s", serial,
                "--no-playback",
                "--record", video_name,
                "--video-bit-rate", "2M",
                "--max-fps", "30"
            ]

            popen_kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "preexec_fn": os.setsid
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            self._scrcpy_process = subprocess.Popen(cmd, **popen_kwargs)
            time.sleep(1.0)

            if self._scrcpy_process.poll() is not None:
                log.error("❌ [Error] scrcpy crashed on startup")

        except FileNotFoundError:
            log.error("❌ [Error] `scrcpy` not found in PATH")
            log.error("❌ [Error] Mac: brew install scrcpy")
            log.error("❌ [Error] Windows: see official docs for PATH setup")
        except Exception as e:
            log.error(f"❌ [Error] Failed to start scrcpy: {e}")

    def stop_record_and_get_path(self, video_name: str) -> str:
        log.info("⏳ [System] Stopping scrcpy, waiting for video flush...")
        if not self._scrcpy_process:
            return ""

        try:
            pgid = os.getpgid(self._scrcpy_process.pid)
            os.killpg(pgid, signal.SIGINT)
            self._scrcpy_process.wait(timeout=5.0)
            log.info("[System] scrcpy exited successfully")
        except subprocess.TimeoutExpired:
            log.warning("[Warning] scrcpy did not exit in time, force killing...")
            try:
                pgid = os.getpgid(self._scrcpy_process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception as e:
                log.error(f"❌ [Error] Failed to kill process group: {e}")
                self._scrcpy_process.kill()
            self._scrcpy_process.wait()
        except OSError as e:
            log.debug(f"[Fallback] Cannot operate on process group, trying direct terminate: {e}")
            try:
                self._scrcpy_process.send_signal(signal.SIGINT)
                self._scrcpy_process.wait(timeout=2)
            except Exception as e:
                log.error(f"❌ [Error] Failed to send SIGINT: {e}")
                self._scrcpy_process.kill()
                self._scrcpy_process.wait()
        except Exception as e:
            log.error(f"❌ [Error] Failed to stop scrcpy: {e}")

        return self._validate_video_file(video_name)

    def take_screenshot(self) -> bytes:
        image = self.driver.screenshot()
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        return img_bytes.getvalue()

    def _validate_video_file(self, video_name: str) -> str:
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
