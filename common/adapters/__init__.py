# 统一导出，让外部只需导入这个文件即可使用所有适配器
from .base_adapter import BasePlatformAdapter
from .android_adapter import AndroidU2Adapter
from .ios_adapter import IosWdaAdapter
from .web_adapter import WebPlaywrightAdapter

__all__ = [
    "BasePlatformAdapter",
    "AndroidU2Adapter",
    "IosWdaAdapter",
    "WebPlaywrightAdapter"
]
