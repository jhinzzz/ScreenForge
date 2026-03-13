import os
from datetime import datetime

import pytest
import allure

from common.logs import log
from common.adapters import AndroidU2Adapter, IosWdaAdapter, WebPlaywrightAdapter

# ==============================================================
# Pytest 命令行注册（仅保留Pytest相关）
# ==============================================================
def pytest_addoption(parser):
    parser.addoption(
        "--platform", action="store", default="android", choices=["android", "ios", "web"],
        help="指定自动化执行的目标平台，默认为 android"
    )

# ==============================================================
# 全局变量 & 夹具（仅保留Pytest相关）
# ==============================================================
_adapter = None  # 全局适配器实例

@pytest.fixture(scope="session")
def d(request):
    """全局设备驱动 fixture，动态实例化不同平台驱动"""
    global _adapter
    platform = request.config.getoption("--platform")
    log.info(f"[System] 初始化 {platform} 设备...")

    # 工厂模式分发适配器
    if platform == "android":
        _adapter = AndroidU2Adapter()
    elif platform == "ios":
        _adapter = IosWdaAdapter()
    elif platform == "web":
        _adapter = WebPlaywrightAdapter()
    else:
        log.error(f"[Error] 不支持的平台: {platform}")
        raise ValueError(f"[Error] 不支持的平台: {platform}")

    _adapter.setup()
    yield _adapter.driver
    _adapter.teardown()

@pytest.fixture(autouse=True)
def auto_record_video(request, d):
    """跨平台通用录像 Fixture"""
    if _adapter is None:
        yield
        return

    # 录像文件路径处理
    video_dir = os.path.abspath(os.path.join("report", "videos"))
    os.makedirs(video_dir, exist_ok=True)
    test_name = request.node.name
    video_filename = os.path.join(video_dir, f"{test_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")

    _adapter.start_record(video_filename)
    log.info(f"[System] 开始执行测试用例: {test_name}")

    yield  # 执行测试用例

    log.info("[System] 测试用例执行完成")
    actual_video_path = _adapter.stop_record_and_get_path(video_filename)

    # 失败挂载录像，成功清理文件
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        if actual_video_path and os.path.exists(actual_video_path):
            allure.attach.file(
                actual_video_path,
                name=f"执行录像_{test_name}",
                attachment_type=allure.attachment_type.MP4
            )
            log.info("[System] 用例失败，已挂载录像至Allure")
    else:
        if actual_video_path and os.path.exists(actual_video_path):
            os.remove(actual_video_path)
            log.info(f"[System] 用例成功，已清理录像文件: {actual_video_path}")

# ==============================================================
# Pytest 钩子（仅保留Pytest相关）
# ==============================================================
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)

    if rep.when == "call" and rep.failed:
        if _adapter is not None:
            try:
                screenshot_bytes = _adapter.take_screenshot()
                if screenshot_bytes:
                    allure.attach(
                        screenshot_bytes,
                        name=f"失败截图_{item.name}",
                        attachment_type=allure.attachment_type.PNG
                    )
                    log.info("[System] 已挂载失败截图至Allure")
            except Exception as e:
                log.error(f"[Error] 捕获失败截图异常: {e}")
