import io

import config.config as config
from common.logs import log

from .base_adapter import BasePlatformAdapter


class IosWdaAdapter(BasePlatformAdapter):
    def setup(self):
        log.info("[System] Initializing iOS (WDA) device...")
        import wda
        self.driver = wda.Client('http://localhost:8100')
        self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)

    def teardown(self):
        log.info("[System] Disconnecting iOS device...")

    def start_record(self, video_name: str):
        log.info("[System] iOS native recording not configured, skipping")

    def stop_record_and_get_path(self, video_name: str) -> str:
        return ""

    def take_screenshot(self) -> bytes:
        image = self.driver.screenshot()
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        return img_bytes.getvalue()
