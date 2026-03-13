import io

class BasePlatformAdapter:
    """多端底层能力适配器基类 (定义统一的标准接口)"""
    def __init__(self):
        self.driver = None

    def setup(self):
        pass

    def teardown(self):
        pass

    def start_record(self, video_name: str):
        pass

    def stop_record_and_get_path(self, video_name: str) -> str:
        return ""

    def take_screenshot(self) -> bytes:
        return b""
