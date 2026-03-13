import io

from common.logs import log
import config.config as config
from .base_adapter import BasePlatformAdapter

class IosWdaAdapter(BasePlatformAdapter):
    """iOS facebook-wda 适配层"""
    def setup(self):
        log.info("[System] 初始化 iOS(WDA) 设备...")
        import wda  # 延迟导入，避免Android环境依赖
        self.driver = wda.Client('http://localhost:8100')
        self.driver.implicitly_wait(config.DEFAULT_TIMEOUT)

    def teardown(self):
        log.info("[System] 断开 iOS 设备...")

    def start_record(self, video_name: str):
        log.info("[System] iOS 暂未配置原生录制引擎，跳过视频录制")

    def stop_record_and_get_path(self, video_name: str) -> str:
        return ""

    def take_screenshot(self) -> bytes:
        image = self.driver.screenshot()
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        return img_bytes.getvalue()
