import os
import shutil
from common.logs import log
import config.config as config
from utils.utils_web import normalize_loopback_url
from .base_adapter import BasePlatformAdapter


def _is_environment_restricted_error(message: str) -> bool:
    text = str(message).lower()
    return any(
        pattern in text
        for pattern in (
            "operation not permitted",
            "permission denied",
            " eperm ",
            "connect eperm",
        )
    )


class WebPlaywrightAdapter(BasePlatformAdapter):
    """Web Playwright 适配层"""

    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.context = None
        self.driver = None  # 规范化：明确声明 driver 属性

        # 视频存放路径
        self.video_dir = os.path.abspath(os.path.join("report", "videos_web"))
        # 定义缓存状态文件(Cookies, LocalStorage)的路径
        self.state_file = os.path.abspath(os.path.join("report", "browser_state.json"))
        # 定义浏览器真实的渲染视口大小 (1080p)
        self.viewport_size = {"width": 1920, "height": 1080}
        # 独立定义录像的分辨率 (720p)。Playwright 会自动将 1080p 的画面缩放为 720p 录制，大幅减小视频体积
        self.video_size = {"width": 1280, "height": 720}

    def setup(self):
        log.info("⏱️ [System] 初始化 Web(Playwright) 浏览器...")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("❌ [Error] 缺少 playwright 库，请执行 `pip install playwright` 并运行 `playwright install`")
            raise

        self.playwright = sync_playwright().start()
        # 通过 CDP 连接已运行的系统 Chrome
        cdp_url = normalize_loopback_url(config.WEB_CDP_URL)
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            if _is_environment_restricted_error(e):
                self.playwright.stop()
                self.playwright = None
                raise RuntimeError(
                    "当前运行环境限制了 Playwright 连接本地 Chrome CDP，"
                    "请在宿主终端中直接运行，或放宽本地网络权限后重试。"
                    f" 原始错误: {e}"
                ) from e
            log.error(
                f"❌ [Error] 无法连接到 Chrome CDP ({config.WEB_CDP_URL})，"
                f"请先在终端启动系统 Chrome：\n"
                f"  macOS: open -a 'Google Chrome' --args --remote-debugging-port=9222\n"
                f"  Linux: google-chrome --remote-debugging-port=9222\n"
                f"  Windows: start chrome --remote-debugging-port=9222\n"
                f"  原始错误: {e}"
            )
            # M-2: 确保已启动的 playwright 后台线程被释放，避免资源泄漏
            self.playwright.stop()
            self.playwright = None
            raise

        # 预先确保视频目录存在
        os.makedirs(self.video_dir, exist_ok=True)

        # 准备新上下文的参数
        context_kwargs = {
            "viewport": self.viewport_size,
            "record_video_dir": self.video_dir,
            "record_video_size": self.video_size,
        }

        # 若存在状态文件，则加载缓存以实现免登录
        if os.path.exists(self.state_file):
            log.info(
                f"✅ [System] 发现浏览器状态缓存，正在加载以恢复会话: {self.state_file}"
            )
            context_kwargs["storage_state"] = self.state_file
        else:
            log.info("⚠️ [Warning] 未找到状态缓存，本次测试可能需要进行登录流程。")

        self.context = self.browser.new_context(**context_kwargs)
        self.driver = self.context.new_page()

        # 统一全局超时时间（毫秒）
        self.driver.set_default_timeout(config.DEFAULT_TIMEOUT * 1000)

    def teardown(self):
        log.info("⏱️ [System] 关闭 Web 浏览器资源并处理缓存...")
        try:
            if self.context:
                try:
                    # 在关闭 context 前保存当前最新的登录状态供下次复用
                    os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                    self.context.storage_state(path=self.state_file)
                    log.info(f"✅ [System] 已成功保存当前浏览器登录状态至: {self.state_file}")
                except Exception as e:
                    log.warning(f"⚠️ [Warning] 保存浏览器状态缓存失败: {e}")
                try:
                    self.context.close()
                except Exception as e:
                    # S-1: context.close 异常不得阻断 playwright.stop，避免后台线程泄漏
                    log.warning(f"⚠️ [Warning] 关闭浏览器 context 失败: {e}")
        finally:
            # CDP 模式下不关闭浏览器进程（由用户自行管理），但确保 playwright 后台线程始终停止
            if self.playwright:
                self.playwright.stop()

    def start_record(self, video_name: str):
        # Playwright 在 new_context 时已经自动开启录制，此处无需额外操作
        log.info("✅ [System] Playwright 原生录制引擎已就绪...")

    def stop_record_and_get_path(self, video_name: str) -> str:
        log.info("⏱️ [System] 正在处理 Playwright 录像文件...")
        if not self.driver or not self.context:
            return ""

        try:
            # 获取 Playwright 自动生成的视频路径
            original_path = self.driver.video.path()

            # 为了确保视频完整写入，先 close page (不影响 Context 记录 state)
            self.driver.close()
            self.driver = None  # S-2: 标记 page 已关闭，避免 teardown 重复操作

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
