import base64
import io
import os
from pathlib import Path

import allure
import pytest

import config.config as config
from common.ai_heal import HealerBrain, HealResult
from common.logs import log
from utils.utils_web import compress_web_dom
from utils.utils_xml import compress_android_xml

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
            getattr(config, "TEST_PLATFORM", "web"),
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
                        "Live platform tests skipped by default. "
                        "Set RUN_LIVE_PLATFORM_TESTS=true and "
                        "TEST_PLATFORM=android|ios|web to enable."
                    )
                )
            )
            continue

        if item_platform and item_platform != selected_platform:
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        f"Only TEST_PLATFORM={selected_platform} is enabled; "
                        f"skipping {item_platform} test."
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
        log.info("📸 Capturing failure screenshot...")
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
                name=f"failure_screenshot_{item.name}",
                attachment_type=allure.attachment_type.PNG,
            )
            log.info("✅ [System] Failure screenshot attached to Allure report")
    except Exception as e:
        log.error(f"[Error] Failed to capture failure screenshot: {e}")
    return img_bytes


def _trigger_self_healing(device, platform_name: str, item, call, img_bytes: bytes):
    log.info("=" * 60)
    log.info("🚑 [Self-Healing] Triggered — analyzing failure scene...")
    log.info("=" * 60)

    if not device:
        log.error("❌ Self-healing engine cannot access fixture 'd'. Aborting.")
        return

    log.info("🔍 Extracting DOM/XML structure for self-healing analysis...")
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
        log.warning(f"⚠️ Partial snapshot capture failure: {e}")

    excinfo = call.excinfo
    error_msg = str(excinfo.value)

    file_path = str(getattr(item, "path", item.fspath))

    if not os.path.exists(file_path):
        log.error(f"❌ Test script file not found: {file_path}. Aborting self-heal.")
        return

    error_line_num = excinfo.traceback[-1].lineno + 1
    for tb_entry in excinfo.traceback:
        if str(tb_entry.path) == file_path:
            error_line_num = tb_entry.lineno + 1
            break

    with open(file_path, "r", encoding="utf-8") as f:
        original_script = f.read()

    import shutil

    healer = HealerBrain()
    result: HealResult = healer.heal_script(
        script_content=original_script,
        error_msg=error_msg,
        error_line_num=error_line_num,
        ui_json=ui_json,
        screenshot_base64=screenshot_base64,
        platform=platform_name,
    )

    if not result.fixed_code:
        log.error("❌ Self-healing engine failed to generate fix code.")
        return

    if result.confidence < config.AUTO_HEAL_MIN_CONFIDENCE:
        log.warning(
            f"⚠️ [Self-Healing] Confidence {result.confidence:.2f} below threshold "
            f"{config.AUTO_HEAL_MIN_CONFIDENCE}. Skipping auto-fix. "
            f"(reason: {result.fix_description})"
        )
        return

    if "def test_" not in result.fixed_code:
        log.error("❌ Self-healing code is malformed (missing test function). Aborting overwrite.")
        return

    # Backup before overwriting
    backup_path = file_path + ".bak"
    shutil.copy2(file_path, backup_path)
    log.info(f"📦 [Self-Healing] Original script backed up to: {backup_path}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result.fixed_code)
    log.info(
        f"✅ [Self-Healing] Script healed successfully (confidence={result.confidence:.2f}, "
        f"desc={result.fix_description})"
    )
    log.info(f"✅ [Self-Healing] Fixed file written to: {file_path}")
    log.info("💡 [Self-Healing] Re-run pytest to verify the healed test case.")


@pytest.fixture(scope="session")
def d():
    from common.adapters import AndroidU2Adapter, IosWdaAdapter, WebPlaywrightAdapter

    platform = os.getenv("TEST_PLATFORM", "web").lower()

    log.info(f"🚀 [Pytest Setup] Initializing {platform} test environment...")
    if platform == "android":
        adapter = AndroidU2Adapter()
    elif platform == "ios":
        adapter = IosWdaAdapter()
    elif platform == "web":
        adapter = WebPlaywrightAdapter()
    else:
        log.warning(f"⚠️ Unrecognized platform '{platform}', falling back to web")
        adapter = WebPlaywrightAdapter()

    adapter.setup()
    yield adapter.driver
    adapter.teardown()
    log.info(f"🏁 [Pytest Teardown] {platform} test environment cleaned up")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        nodeid = item.nodeid
        _failure_tracker[nodeid] = _failure_tracker.get(nodeid, 0) + 1
        current_fails = _failure_tracker[nodeid]

        log.warning(f"⚠️ Test failure detected: {nodeid} (consecutive failures: {current_fails})")

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
