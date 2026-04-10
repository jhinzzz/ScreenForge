import io
import os
import sys
import time
import signal
import subprocess
from common.logs import log
import config.config as config
from .base_adapter import BasePlatformAdapter

class AndroidU2Adapter(BasePlatformAdapter):
    """Android uiautomator2 适配层"""
    def __init__(self):
        super().__init__()
        self._scrcpy_process = None

    def setup(self):
        import uiautomator2 as u2
        log.info("⏳ [Pytest Setup] 正在初始化 Android(u2) 设备...")
        self.driver = u2.connect()
        self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)

    def teardown(self):
        log.info("⏳ [Pytest Teardown] 正在断开 Android(u2) 设备...")

    def start_record(self, video_name: str):
        log.info("⏳ [Pytest Setup] 📹 正在启动 scrcpy 引擎进行录像...")
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
                log.error("❌ [Error] scrcpy 启动闪退")

        except FileNotFoundError:
            log.error("❌ [Error] 系统环境未找到 `scrcpy` 命令")
            log.error("❌ [Error] Mac 安装: brew install scrcpy")
            log.error("❌ [Error] Windows 安装请参考官方文档配置系统环境变量。")
        except Exception as e:
            log.error(f"❌ [Error] 启动 scrcpy 异常: {e}")

    def stop_record_and_get_path(self, video_name: str) -> str:
        log.info("⏳ [System] 正在终止 scrcpy，等待视频流封包...")
        if not self._scrcpy_process:
            return ""

        try:
            pgid = os.getpgid(self._scrcpy_process.pid)
            os.killpg(pgid, signal.SIGINT)
            self._scrcpy_process.wait(timeout=5.0)
            log.info("[System] scrcpy 已成功退出")
        except subprocess.TimeoutExpired:
            log.warning("[Warning] scrcpy 未及时退出，强制 Kill 进程组...")
            try:
                pgid = os.getpgid(self._scrcpy_process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception as e:
                log.error(f"❌ [Error] 强制 Kill 进程组失败: {e}")
                self._scrcpy_process.kill()
            self._scrcpy_process.wait()
        except OSError as e:
            log.debug(f"❌ [Fallback] 无法操作进程组，尝试直接终止: {e}")
            try:
                self._scrcpy_process.send_signal(signal.SIGINT)
                self._scrcpy_process.wait(timeout=2)
            except Exception as e:
                log.error(f"❌ [Error] 发送 SIGINT 信号失败: {e}")
                self._scrcpy_process.kill()
                self._scrcpy_process.wait()
        except Exception as e:
            log.error(f"❌ [Error] 停止 scrcpy 发生异常: {e}")

        return self._validate_video_file(video_name)

    def take_screenshot(self) -> bytes:
        image = self.driver.screenshot()
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        return img_bytes.getvalue()

    def _validate_video_file(self, video_name: str) -> str:
        """校验录像文件是否存在且大小正常"""
        if os.path.exists(video_name):
            file_size = os.path.getsize(video_name)
            if file_size < 1024:
                log.warning(f"⚠️ [Warning] 录像文件大小异常： {file_size} bytes")
            else:
                log.info(f"✅ [System] 录像已成功落盘 (大小: {file_size // 1024} KB)")
            return video_name
        else:
            log.error(f"❌ [Error] 未找到录像文件: {video_name}")
            return ""
