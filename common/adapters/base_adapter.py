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

    def start_record(self, video_name: str):
        pass

    def stop_record_and_get_path(self, video_name: str) -> str:
        return ""
