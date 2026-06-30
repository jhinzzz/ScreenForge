from abc import ABC, abstractmethod


class BasePlatformAdapter(ABC):
    def __init__(self):
        self.driver = None

    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def teardown(self):
        pass

    @abstractmethod
    def take_screenshot(self) -> bytes:
        pass

    # 录像 seam（诚实边界）：
    #   - android/ios：start_record/stop_record_and_get_path 落真视频文件（scrcpy / simctl）。
    #   - web：start_record 是 no-op（CDP attach 无法用 Playwright 录像）；web 的"录像"
    #     由 review 层用逐操作截图 ffmpeg 拼胶片（review/render.py make_filmstrip）实现，
    #     不走本 seam。调用方须把返回 "" / None 当作"无视频"，非错误。
    def start_record(self, video_name: str):
        pass

    def stop_record_and_get_path(self, video_name: str) -> str:
        return ""
