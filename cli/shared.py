"""Shared lazy proxies, adapter factories, and utility functions."""

import base64
import time

from common.capabilities import (
    ACTIONS_REQUIRING_EXTRA_VALUE,
    GLOBAL_ACTIONS,
    SUPPORTED_ACTIONS,
)


class _LazyProxy:
    def __init__(self, loader):
        object.__setattr__(self, "_loader", loader)
        object.__setattr__(self, "_value", None)

    def _load(self):
        value = object.__getattribute__(self, "_value")
        if value is None:
            value = object.__getattribute__(self, "_loader")()
            object.__setattr__(self, "_value", value)
        return value

    def __getattr__(self, name):
        return getattr(self._load(), name)

    def __setattr__(self, name, value):
        if name in {"_loader", "_value"}:
            object.__setattr__(self, name, value)
            return
        setattr(self._load(), name, value)


def _load_config_module():
    import config.config as _config

    return _config


def _load_log_object():
    from common.logs import log as _log

    return _log


config = _LazyProxy(_load_config_module)
log = _LazyProxy(_load_log_object)
UIExecutor = None
get_actual_element = None
StepHistoryManager = None
run_preflight = None
RunReporter = None
compress_web_dom = None
compress_android_xml = None
AndroidU2Adapter = None
IosWdaAdapter = None
WebPlaywrightAdapter = None
AutonomousBrain = None
load_workflow_file = None
WorkflowLoadError = None
parse_workflow_var_overrides = None
resolve_workflow_definition = None
SUPPORTED_INLINE_ACTIONS = SUPPORTED_ACTIONS
GLOBAL_INLINE_ACTIONS = GLOBAL_ACTIONS
INLINE_ACTIONS_REQUIRING_EXTRA_VALUE = ACTIONS_REQUIRING_EXTRA_VALUE


def get_initial_header() -> list:
    from main import get_initial_header as _get_initial_header

    return _get_initial_header()


def save_to_disk(file_path: str, content: list) -> None:
    from main import save_to_disk as _save_to_disk

    _save_to_disk(file_path, content)


def launch_app(device, env_name="dev", system="android"):
    from main import launch_app as _launch_app

    return _launch_app(device, env_name, system)


def _ensure_executor_runtime() -> None:
    global UIExecutor, get_actual_element
    if UIExecutor is None or get_actual_element is None:
        from common.executor import (
            UIExecutor as _UIExecutor,
            get_actual_element as _get_actual_element,
        )

        if UIExecutor is None:
            UIExecutor = _UIExecutor
        if get_actual_element is None:
            get_actual_element = _get_actual_element


def _ensure_history_manager() -> None:
    global StepHistoryManager
    if StepHistoryManager is None:
        from common.history_manager import StepHistoryManager as _StepHistoryManager

        StepHistoryManager = _StepHistoryManager


def _ensure_preflight_runner() -> None:
    global run_preflight
    if run_preflight is None:
        from common.preflight import run_preflight as _run_preflight

        run_preflight = _run_preflight


def _ensure_reporter_class() -> None:
    global RunReporter
    if RunReporter is None:
        from common.run_reporter import RunReporter as _RunReporter

        RunReporter = _RunReporter


def _ensure_ui_compressors() -> None:
    global compress_web_dom, compress_android_xml
    if compress_web_dom is None:
        from utils.utils_web import compress_web_dom as _compress_web_dom

        compress_web_dom = _compress_web_dom
    if compress_android_xml is None:
        from utils.utils_xml import compress_android_xml as _compress_android_xml

        compress_android_xml = _compress_android_xml


def _ensure_adapter_factories() -> None:
    global AndroidU2Adapter, IosWdaAdapter, WebPlaywrightAdapter
    if (
        AndroidU2Adapter is None
        or IosWdaAdapter is None
        or WebPlaywrightAdapter is None
    ):
        from common.adapters import (
            AndroidU2Adapter as _AndroidU2Adapter,
            IosWdaAdapter as _IosWdaAdapter,
            WebPlaywrightAdapter as _WebPlaywrightAdapter,
        )

        if AndroidU2Adapter is None:
            AndroidU2Adapter = _AndroidU2Adapter
        if IosWdaAdapter is None:
            IosWdaAdapter = _IosWdaAdapter
        if WebPlaywrightAdapter is None:
            WebPlaywrightAdapter = _WebPlaywrightAdapter


def _ensure_runtime_classes() -> None:
    global AutonomousBrain
    if AutonomousBrain is None:
        from common.ai_autonomous import AutonomousBrain as _AutonomousBrain

        AutonomousBrain = _AutonomousBrain


def _ensure_workflow_loader() -> None:
    global load_workflow_file
    global WorkflowLoadError
    global parse_workflow_var_overrides
    global resolve_workflow_definition
    if (
        load_workflow_file is None
        or WorkflowLoadError is None
        or parse_workflow_var_overrides is None
        or resolve_workflow_definition is None
    ):
        from common.workflow_schema import (
            WorkflowLoadError as _WorkflowLoadError,
            load_workflow_file as _load_workflow_file,
            parse_workflow_var_overrides as _parse_workflow_var_overrides,
            resolve_workflow_definition as _resolve_workflow_definition,
        )

        if load_workflow_file is None:
            load_workflow_file = _load_workflow_file
        if WorkflowLoadError is None:
            WorkflowLoadError = _WorkflowLoadError
        if parse_workflow_var_overrides is None:
            parse_workflow_var_overrides = _parse_workflow_var_overrides
        if resolve_workflow_definition is None:
            resolve_workflow_definition = _resolve_workflow_definition


def _create_adapter(platform: str):
    _ensure_adapter_factories()
    if platform == "android":
        return AndroidU2Adapter()
    if platform == "ios":
        return IosWdaAdapter()
    if platform == "web":
        return WebPlaywrightAdapter()
    raise ValueError(f"不支持的平台: {platform}")


def _connect_adapter(args, reporter):
    adapter = _create_adapter(args.platform)
    adapter.setup()
    device = adapter.driver
    log.info(f"✅ {args.platform} 平台已连接并初始化完成")
    try:
        launch_app(device, args.env, args.platform)
        reporter.emit_event("adapter_ready", platform=args.platform)
        return adapter
    except Exception:
        try:
            adapter.teardown()
        except Exception as e:
            log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")
        raise


def _wait_for_platform_idle(platform: str, device) -> None:
    try:
        if platform == "android":
            device.wait_activity(device.app_current()["activity"], timeout=3)
        elif platform == "web":
            device.wait_for_load_state("domcontentloaded")
    except Exception:
        time.sleep(1)


def _capture_ui_state(args, adapter, reporter, step_index: int):
    device = adapter.driver
    _wait_for_platform_idle(args.platform, device)
    _ensure_ui_compressors()

    ui_json = "{}"
    if args.platform == "android":
        try:
            ui_json = compress_android_xml(device.dump_hierarchy())
        except Exception as e:
            log.warning(f"⚠️ 抓取 UI 树失败: {e}")
    elif args.platform == "web":
        try:
            ui_json = compress_web_dom(device)
        except Exception as e:
            log.warning(f"⚠️ 抓取 Web DOM 失败: {e}")

    screenshot_base64 = None
    if args.vision:
        try:
            img_bytes = adapter.take_screenshot()
            reporter.save_screenshot(img_bytes, step_index)
            screenshot_base64 = base64.b64encode(img_bytes).decode("utf-8")
            log.info("📸 已截取当前屏幕画面，准备发送给视觉大模型。")
        except Exception as e:
            log.warning(f"⚠️ 截图失败，将降级为纯文本树模式: {e}")

    return ui_json, screenshot_base64


class _SharedAdapterManager:
    """MCP session 内的共享 adapter 管理器。

    同一 platform 的 adapter 只创建一次，后续请求直接复用。
    MCP server 退出时调用 teardown_all 统一清理。
    """

    def __init__(self):
        self._adapters: dict[str, object] = {}

    def get_or_create(self, platform: str, env: str = "dev"):
        if platform in self._adapters:
            adapter = self._adapters[platform]
            log.info(f"♻️ [System] 复用已有 {platform} adapter")
            return adapter
        from cli.parser import build_parser
        from cli.tool_protocol_handlers import _NullRunReporter

        parser = build_parser()
        args = parser.parse_args([])
        args.platform = platform
        args.env = env
        adapter = _connect_adapter(args, _NullRunReporter())
        self._adapters[platform] = adapter
        return adapter

    def teardown_all(self):
        for platform, adapter in self._adapters.items():
            try:
                adapter.teardown()
                log.info(f"✅ [System] 已清理 {platform} adapter")
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理 {platform} adapter 失败: {e}")
        self._adapters.clear()
