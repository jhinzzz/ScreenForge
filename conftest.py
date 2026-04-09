import os
import io
import base64
from pathlib import Path
import pytest
import allure
from common.logs import log
from utils.utils_xml import compress_android_xml
from utils.utils_web import compress_web_dom
from common.ai_heal import HealerBrain
import config.config as config

_failure_tracker = {}
_LIVE_PLATFORM_DIRS = {"android", "ios", "web"}


def _is_live_platform_test_path(path: str) -> bool:
    parts = Path(str(path)).parts
    for index, part in enumerate(parts):
        if part == "test_cases" and index + 1 < len(parts):
            return parts[index + 1] in _LIVE_PLATFORM_DIRS
    return False


def _get_live_platform_from_path(path: str) -> str:
    parts = Path(str(path)).parts
    for index, part in enumerate(parts):
        if part == "test_cases" and index + 1 < len(parts):
            platform = parts[index + 1]
            if platform in _LIVE_PLATFORM_DIRS:
                return platform
    return ""


def _is_live_platform_execution_enabled() -> bool:
    raw_value = os.getenv(
        "RUN_LIVE_PLATFORM_TESTS",
        str(getattr(config, "RUN_LIVE_PLATFORM_TESTS", False)),
    )
    return str(raw_value).lower() in ("true", "1", "t", "yes")


def _get_selected_live_platform() -> str:
    return str(
        os.getenv(
            "TEST_PLATFORM",
            getattr(config, "TEST_PLATFORM", "android"),
        )
    ).lower()


def pytest_collection_modifyitems(config, items):
    live_execution_enabled = _is_live_platform_execution_enabled()
    selected_platform = _get_selected_live_platform()

    for item in items:
        if not _is_live_platform_test_path(str(getattr(item, "fspath", item.path))):
            continue

        item.add_marker(pytest.mark.live_platform)
        item_platform = _get_live_platform_from_path(str(getattr(item, "fspath", item.path)))

        if not live_execution_enabled:
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "默认跳过真机/真浏览器回放测试；如需执行，请设置 "
                        "RUN_LIVE_PLATFORM_TESTS=true，并按需设置 "
                        "TEST_PLATFORM=android|ios|web。"
                    )
                )
            )
            continue

        if item_platform and item_platform != selected_platform:
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        f"当前仅启用 TEST_PLATFORM={selected_platform} 的真机回放测试，"
                        f"已跳过 {item_platform} 平台脚本。"
                    )
                )
            )


def _normalize_screenshot_bytes(raw) -> bytes:
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        return base64.b64decode(raw)
    if hasattr(raw, "save"):
        img_bytes = io.BytesIO()
        raw.save(img_bytes, format="PNG")
        return img_bytes.getvalue()
    return None


def _capture_failure_screenshot(device, platform_name: str, item) -> bytes:
    img_bytes = None
    try:
        log.info("📸 正在采集失败现场截图...")
        if platform_name == "android":
            img_bytes = _normalize_screenshot_bytes(device.screenshot())
        elif platform_name == "ios":
            raw = device.screenshot()
            try:
                img_bytes = _normalize_screenshot_bytes(raw)
            except Exception:
                img_bytes = None
        elif platform_name == "web":
            img_bytes = _normalize_screenshot_bytes(device.screenshot())

        if img_bytes:
            allure.attach(
                img_bytes,
                name=f"失败截图_{item.name}",
                attachment_type=allure.attachment_type.PNG,
            )
            log.info(f"✅ [System] 已成功将失败截图挂载至 Allure 报告")
    except Exception as e:
        log.error(f"[Error] 捕获失败截图异常: {e}")
    return img_bytes


def _trigger_self_healing(device, platform_name: str, item, call, img_bytes: bytes):
    log.info("=" * 60)
    log.info("🚑 [Self-Healing] 触发自动化自愈机制，正在介入案发现场...")
    log.info("=" * 60)

    if not device:
        log.error("❌ 自愈引擎无法获取 fixture 'd'，终止自愈。")
        return

    log.info("🔍 正在提取 DOM/XML 结构用于自愈分析...")
    ui_json = "{}"
    screenshot_base64 = None

    try:
        if platform_name == "android":
            ui_json = compress_android_xml(device.dump_hierarchy())
        elif platform_name == "web":
            ui_json = compress_web_dom(device)

        if img_bytes:
            screenshot_base64 = base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        log.warning(f"⚠️ 现场快照采集出现部分缺失: {e}")

    excinfo = call.excinfo
    error_msg = str(excinfo.value)

    file_path = str(getattr(item, "path", item.fspath))

    if not os.path.exists(file_path):
        log.error(f"❌ 找不到测试脚本文件: {file_path}，终止自愈。")
        return

    error_line_num = excinfo.traceback[-1].lineno + 1
    for tb_entry in excinfo.traceback:
        if str(tb_entry.path) == file_path:
            error_line_num = tb_entry.lineno + 1
            break

    with open(file_path, "r", encoding="utf-8") as f:
        original_script = f.read()

    healer = HealerBrain()
    fixed_code = healer.heal_script(
        script_content=original_script,
        error_msg=error_msg,
        error_line_num=error_line_num,
        ui_json=ui_json,
        screenshot_base64=screenshot_base64,
        platform=platform_name,
    )

    if fixed_code:
        if "def test_" in fixed_code:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fixed_code)
            log.info("✅ [Self-Healing] 脚本自愈手术成功！")
            log.info(f"✅ [Self-Healing] 修复文件已精准落盘: {file_path}")
            log.info("💡 [Self-Healing] 提示: 您可以重新运行 pytest 体验修复后的用例。")
        else:
            log.error("❌ 自愈引擎返回的代码结构异常，放弃覆盖文件。")
    else:
        log.error("❌ 自愈引擎未能生成修复代码。")


@pytest.fixture(scope="session")
def d():
    from common.adapters import AndroidU2Adapter, IosWdaAdapter, WebPlaywrightAdapter

    platform = os.getenv("TEST_PLATFORM", "android").lower()

    log.info(f"🚀 [Pytest Setup] 正在初始化 {platform} 测试环境...")
    if platform == "android":
        adapter = AndroidU2Adapter()
    elif platform == "ios":
        adapter = IosWdaAdapter()
    elif platform == "web":
        adapter = WebPlaywrightAdapter()
    else:
        log.warning(f"⚠️ 未识别平台 '{platform}'，默认回退到 android")
        adapter = AndroidU2Adapter()

    adapter.setup()
    yield adapter.driver
    adapter.teardown()
    log.info(f"🏁 [Pytest Teardown] {platform} 测试环境已清理")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        nodeid = item.nodeid
        _failure_tracker[nodeid] = _failure_tracker.get(nodeid, 0) + 1
        current_fails = _failure_tracker[nodeid]

        log.warning(f"⚠️ 检测到用例失败: {nodeid} (当前连续失败次数: {current_fails})")

        device = item.funcargs.get("d")
        platform_name = "android"
        img_bytes = None

        if device:
            if device.__class__.__name__ == "Page":
                platform_name = "web"
            elif "ios" in str(device.__class__).lower():
                platform_name = "ios"

            img_bytes = _capture_failure_screenshot(device, platform_name, item)

        if (
            current_fails == config.AUTO_HEAL_TRIGGER_THRESHOLD
            and config.AUTO_HEAL_ENABLED
        ):
            _trigger_self_healing(device, platform_name, item, call, img_bytes)
