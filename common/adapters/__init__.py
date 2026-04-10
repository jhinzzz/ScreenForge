# 统一导出，让外部只需导入这个文件即可使用所有适配器
# 使用惰性导入，避免 Web-only 用户被迫安装 uiautomator2 / facebook-wda
from .base_adapter import BasePlatformAdapter

__all__ = [
    "BasePlatformAdapter",
    "AndroidU2Adapter",
    "IosWdaAdapter",
    "WebPlaywrightAdapter",
]


def __getattr__(name: str):
    if name == "AndroidU2Adapter":
        from .android_adapter import AndroidU2Adapter
        return AndroidU2Adapter
    if name == "IosWdaAdapter":
        from .ios_adapter import IosWdaAdapter
        return IosWdaAdapter
    if name == "WebPlaywrightAdapter":
        from .web_adapter import WebPlaywrightAdapter
        return WebPlaywrightAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
