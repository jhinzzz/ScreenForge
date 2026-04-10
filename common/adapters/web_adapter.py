import json
import os
import shutil
import subprocess
import time
from common.logs import log
import config.config as config
from .base_adapter import BasePlatformAdapter

_SESSION_FILE = os.path.abspath(os.path.join("report", "web_session.json"))
_CDP_PORT = 9333  # 使用独立端口，避免与用户自己的 Chrome 冲突


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


def _find_chromium_path() -> str:
    """找到 Playwright 安装的 Chromium 可执行文件路径"""
    try:
        import subprocess as sp
        result = sp.run(
            ["python", "-c", "from playwright._impl._driver import compute_driver_executable; print(compute_driver_executable())"],
            capture_output=True, text=True, cwd=os.getcwd(),
        )
        driver_path = result.stdout.strip()
        if driver_path:
            # playwright driver 在 node_modules/.cache/ms-playwright 附近
            # 用 playwright 的 API 来获取更可靠
            pass
    except Exception:
        pass

    # 直接用 playwright 的 registry 查找
    try:
        from playwright._impl._driver import compute_driver_executable
        import pathlib
        driver = pathlib.Path(compute_driver_executable())
        # Chromium 通常在 driver 同级的 package/.local-browsers 或系统缓存目录
        # 最可靠的方式：用 playwright 自己 launch 一次拿到 executable_path
    except Exception:
        pass

    return ""


class WebPlaywrightAdapter(BasePlatformAdapter):
    """Web Playwright 适配层（持久 session 模式）

    浏览器以独立进程运行，不随 Playwright 连接的断开而关闭。
    - 首次 setup()：launch Chromium 子进程 + CDP，保存 session
    - 后续 setup()：通过 CDP reconnect 到已有浏览器
    - teardown()：保存状态，断开 Playwright 连接，浏览器进程继续运行
    """

    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.context = None
        self.driver = None
        self._chromium_process = None

        self.video_dir = os.path.abspath(os.path.join("report", "videos_web"))
        self.state_file = os.path.abspath(os.path.join("report", "browser_state.json"))
        self.viewport_size = {"width": 1920, "height": 1080}
        self.video_size = {"width": 1280, "height": 720}

    def setup(self):
        log.info("⏱️ [System] 初始化 Web(Playwright) 浏览器...")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("❌ [Error] 缺少 playwright 库，请执行 `pip install playwright` 并运行 `playwright install`")
            raise

        self.playwright = sync_playwright().start()

        # 尝试 reconnect 到已有的持久浏览器
        if self._try_reconnect():
            return

        # 没有已有浏览器，启动新的
        self._launch_persistent_browser()

    def _try_reconnect(self) -> bool:
        """尝试 reconnect 到已有的持久浏览器 session"""
        session = _read_session()
        if not session:
            return False

        cdp_url = session.get("cdp_url", "")
        pid = session.get("pid", 0)

        if not cdp_url or not _is_process_alive(pid):
            log.info("⚠️ [System] 持久浏览器已不存在，将启动新浏览器")
            _clear_session()
            return False

        try:
            self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
            log.info("✅ [System] 已 reconnect 到持久浏览器 session")

            # 复用已有的 context 和 page
            if self.browser.contexts:
                self.context = self.browser.contexts[0]
                if self.context.pages:
                    self.driver = self.context.pages[0]
                    self.driver.set_default_timeout(config.DEFAULT_TIMEOUT * 1000)
                    log.info(f"✅ [System] 复用已有页面: {self.driver.url}")
                    return True

            # 有 browser 但没有 page，创建新的
            self._create_context_and_page()
            return True

        except Exception as e:
            log.info(f"⚠️ [System] reconnect 失败 ({e})，将启动新浏览器")
            _clear_session()
            return False

    def _launch_persistent_browser(self):
        """通过 Playwright 启动独立的 Chromium 进程（带 CDP 端口）"""
        # 用 Playwright 的 launch_server 获取可执行文件路径
        # 然后用 subprocess 手动启动，这样进程不受 playwright.stop() 影响
        chromium_path = self.playwright.chromium.executable_path
        if not chromium_path or not os.path.exists(chromium_path):
            log.error("❌ [Error] 未找到 Playwright Chromium，请执行 `playwright install chromium`")
            raise RuntimeError("Playwright Chromium not found")

        cdp_url = f"http://127.0.0.1:{_CDP_PORT}"
        user_data_dir = os.path.abspath(os.path.join("report", "chromium_profile"))
        os.makedirs(user_data_dir, exist_ok=True)

        log.info(f"🚀 [System] 启动持久 Chromium 进程 (CDP: {cdp_url})...")
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

        # 等待 CDP 端口就绪
        for _ in range(30):
            try:
                import urllib.request
                urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"Chromium CDP 端口 {_CDP_PORT} 启动超时")

        # 保存 session 信息
        _write_session(cdp_url, self._chromium_process.pid)

        # 通过 CDP 连接
        self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
        log.info("✅ [System] 持久 Chromium 已启动并连接成功")

        # 复用或创建 page
        if self.browser.contexts and self.browser.contexts[0].pages:
            self.context = self.browser.contexts[0]
            self.driver = self.context.pages[0]
            self.driver.set_default_timeout(config.DEFAULT_TIMEOUT * 1000)
        else:
            self._create_context_and_page()

    def _create_context_and_page(self):
        """在 default context 中创建新 page。

        CDP 连接模式下，browser.new_context() 创建的 BrowserContext
        在 Playwright 断开后不会被浏览器保留。因此必须复用 default context，
        这样 page 才能跨连接持久化。
        """
        os.makedirs(self.video_dir, exist_ok=True)

        # 优先使用浏览器的 default context（CDP 模式下 contexts[0]）
        if self.browser.contexts:
            self.context = self.browser.contexts[0]
        else:
            self.context = self.browser.new_context(viewport=self.viewport_size)

        # 尝试恢复 storage state（cookie/localStorage）
        if os.path.exists(self.state_file):
            try:
                import json as _json
                with open(self.state_file, "r") as f:
                    state = _json.load(f)
                for cookie in state.get("cookies", []):
                    self.context.add_cookies([cookie])
                log.info(f"✅ [System] 发现浏览器状态缓存，已恢复 cookies: {self.state_file}")
            except Exception as e:
                log.warning(f"⚠️ [Warning] 恢复浏览器状态缓存失败: {e}")

        self.driver = self.context.new_page()
        self.driver.set_default_timeout(config.DEFAULT_TIMEOUT * 1000)

    def teardown(self):
        """断开连接但不杀浏览器——浏览器留给下次调用复用"""
        log.info("⏱️ [System] 保存状态并断开浏览器连接（浏览器保持运行）...")
        try:
            if self.context:
                try:
                    os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                    self.context.storage_state(path=self.state_file)
                    log.info(f"✅ [System] 已成功保存当前浏览器登录状态至: {self.state_file}")
                except Exception as e:
                    log.warning(f"⚠️ [Warning] 保存浏览器状态缓存失败: {e}")
        finally:
            # 只停止 Playwright 连接线程，不关闭浏览器进程
            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception:
                    pass

    def start_record(self, video_name: str):
        log.info("✅ [System] Playwright 原生录制引擎已就绪...")

    def stop_record_and_get_path(self, video_name: str) -> str:
        log.info("⏱️ [System] 正在处理 Playwright 录像文件...")
        if not self.driver or not self.context:
            return ""

        try:
            original_path = self.driver.video.path()
            self.driver.close()
            self.driver = None

            if os.path.exists(original_path):
                shutil.move(original_path, video_name)
                return video_name
            else:
                log.warning(f"⚠️ [Warning] Playwright 视频文件不存在: {original_path}")
        except Exception as e:
            log.error(f"❌ [Error] 获取 Web 录像失败: {e}")

        return ""

    def take_screenshot(self) -> bytes:
        if self.driver:
            return self.driver.screenshot()
        return b""
