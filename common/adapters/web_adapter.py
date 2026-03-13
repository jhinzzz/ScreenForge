from common.logs import log
from .base_adapter import BasePlatformAdapter

class WebPlaywrightAdapter(BasePlatformAdapter):
    """Web Playwright 适配层"""
    def setup(self):
        log.info("[System] 初始化 Web(Playwright) 浏览器...")
        # 后续补充Playwright初始化逻辑
        pass

    def teardown(self):
        pass

    def start_record(self, video_name: str):
        pass

    def stop_record_and_get_path(self, video_name: str) -> str:
        return ""

    def take_screenshot(self) -> bytes:
        return b""
