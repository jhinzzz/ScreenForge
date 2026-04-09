import argparse
import base64
import json
import os
import sys
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from common.capabilities import (
    ACTIONS_REQUIRING_EXTRA_VALUE,
    GLOBAL_ACTIONS,
    SUPPORTED_ACTIONS,
    get_capabilities_payload,
)
from common.run_resume import RunContextLoadError, load_run_bundle, load_run_context
from common.runtime_modes import (
    MODE_DOCTOR,
    MODE_DRY_RUN,
    MODE_PLAN_ONLY,
    MODE_RUN,
    resolve_execution_mode,
)
from common.tool_protocol import (
    ToolRequestError,
    build_capabilities_response,
    build_cli_arg_overrides,
    load_tool_request,
    load_tool_request_from_stdin,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多端自动化测试自主 Agent 底层执行器")
    parser.add_argument("--goal", type=str, default="", help="宏观测试目标")
    parser.add_argument(
        "--context", type=str, default="", help="包含 PRD、用例详细说明的文件路径"
    )
    parser.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "prod", "us_dev", "us_prod"],
        help="测试环境",
    )
    parser.add_argument("--max_steps", type=int, default=15, help="最大自主探索步数")
    parser.add_argument(
        "--max_retries",
        type=int,
        default=3,
        help="单步操作的最大连续容错重试次数，防 Token 消耗死循环",
    )
    parser.add_argument(
        "--output", type=str, default="", help="指定生成的 pytest 脚本路径"
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="android",
        choices=["android", "ios", "web"],
        help="目标测试平台",
    )
    parser.add_argument(
        "--vision", action="store_true", help="是否开启多模态(视觉)模式"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="是否向 stdout 输出结构化 JSON 事件，便于上层 Agent 解析",
    )
    parser.add_argument(
        "--doctor", action="store_true", help="仅执行环境体检，不启动测试执行"
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="基于当前页面生成执行计划，但不执行物理动作",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟执行链路并输出 would-execute 结果，但不执行物理动作",
    )
    parser.add_argument(
        "--resume-run-id",
        type=str,
        default="",
        help="从 report/runs/<run_id>/ 中恢复最小上下文",
    )
    parser.add_argument(
        "--workflow",
        type=str,
        default="",
        help="指定结构化 workflow YAML 文件路径，启用半结构化执行模式",
    )
    parser.add_argument(
        "--workflow-var",
        action="append",
        default=[],
        help="覆盖 workflow 变量，格式为 KEY=VALUE，可重复传入",
    )
    parser.add_argument(
        "--action",
        type=str,
        default="",
        help="指定单步即时动作，启用最小控制面模式",
    )
    parser.add_argument(
        "--action-name",
        type=str,
        default="",
        help="指定单步即时动作的人类可读名称",
    )
    parser.add_argument(
        "--locator-type",
        type=str,
        default="",
        help="指定单步即时动作的定位器类型",
    )
    parser.add_argument(
        "--locator-value",
        type=str,
        default="",
        help="指定单步即时动作的定位器值",
    )
    parser.add_argument(
        "--extra-value",
        type=str,
        default="",
        help="指定单步即时动作附加值，如输入内容、按键名或期望文本",
    )
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="输出当前 CLI 已落地能力的机器可读快照",
    )
    parser.add_argument(
        "--tool-request",
        type=str,
        default="",
        help="从 JSON 文件读取机器可读请求并返回统一 JSON 响应",
    )
    parser.add_argument(
        "--tool-stdin",
        action="store_true",
        help="从 stdin 读取机器可读请求并返回统一 JSON 响应",
    )
    parser.add_argument(
        "--mcp-server",
        action="store_true",
        help="以 stdio 模式启动最小 MCP server，供外部 Agent 原生接入",
    )
    return parser


def validate_cli_args(args) -> None:
    resolve_execution_mode(
        doctor=args.doctor,
        plan_only=args.plan_only,
        dry_run=args.dry_run,
    )
    has_goal = bool(str(args.goal).strip())
    has_workflow = bool(str(getattr(args, "workflow", "")).strip())
    has_action = bool(str(getattr(args, "action", "")).strip())
    has_capabilities = bool(getattr(args, "capabilities", False))
    has_tool_request = bool(str(getattr(args, "tool_request", "")).strip())
    has_tool_stdin = bool(getattr(args, "tool_stdin", False))
    has_mcp_server = bool(getattr(args, "mcp_server", False))
    if has_tool_request and has_tool_stdin:
        raise ValueError("--tool-request 不能与 --tool-stdin 同时使用")
    if has_mcp_server:
        if any(
            [
                has_capabilities,
                has_tool_request,
                has_tool_stdin,
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                bool(str(getattr(args, "resume_run_id", "")).strip()),
            ]
        ):
            raise ValueError("--mcp-server 不能与执行类参数同时使用")
        return
    if has_tool_request:
        if any(
            [
                has_capabilities,
                has_tool_stdin,
                has_mcp_server,
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                bool(str(getattr(args, "resume_run_id", "")).strip()),
            ]
        ):
            raise ValueError("--tool-request 不能与执行类参数同时使用")
        return
    if has_tool_stdin:
        if any(
            [
                has_capabilities,
                has_mcp_server,
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                bool(str(getattr(args, "resume_run_id", "")).strip()),
            ]
        ):
            raise ValueError("--tool-stdin 不能与执行类参数同时使用")
        return
    if has_capabilities:
        if any(
            [
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                has_tool_stdin,
                has_mcp_server,
                bool(str(getattr(args, "resume_run_id", "")).strip()),
            ]
        ):
            raise ValueError("--capabilities 不能与执行类参数同时使用")
        return
    if has_goal and has_workflow:
        raise ValueError("--workflow 模式下不能同时提供 --goal")
    if has_action and (has_goal or has_workflow):
        raise ValueError("--action 模式下不能同时提供 --goal 或 --workflow")
    if not args.doctor and not has_goal and not has_workflow and not has_action:
        raise ValueError("非 doctor 模式必须提供 --goal、--workflow 或 --action")
    if has_workflow:
        for item in getattr(args, "workflow_var", []) or []:
            if "=" not in str(item):
                raise ValueError("workflow 变量覆盖格式必须为 KEY=VALUE")
    if has_action:
        action = str(args.action).strip()
        if action not in SUPPORTED_INLINE_ACTIONS:
            raise ValueError(f"不支持的即时动作类型: {action}")
        if action not in GLOBAL_INLINE_ACTIONS:
            if not str(getattr(args, "locator_type", "")).strip() or not str(
                getattr(args, "locator_value", "")
            ).strip():
                raise ValueError("元素类即时动作必须提供 locator_type 和 locator_value")
        if action in INLINE_ACTIONS_REQUIRING_EXTRA_VALUE and not str(
            getattr(args, "extra_value", "")
        ).strip():
            raise ValueError("该即时动作必须提供 extra_value")


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


def _load_workflow_definition(args):
    _ensure_workflow_loader()
    workflow = load_workflow_file(args.workflow)
    workflow_var_overrides = parse_workflow_var_overrides(args.workflow_var)
    workflow = resolve_workflow_definition(workflow, workflow_var_overrides)

    if workflow.platform and workflow.platform != args.platform:
        raise WorkflowLoadError(
            f"workflow 平台 [{workflow.platform}] 与当前 --platform [{args.platform}] 不一致"
        )

    return workflow


def _workflow_step_display_name(step, index: int) -> str:
    if getattr(step, "name", ""):
        return step.name
    locator_value = getattr(step, "locator_value", "")
    if locator_value and str(locator_value).lower() != "global":
        return f"{step.action}:{locator_value}"
    return f"step_{index}"


def _workflow_step_to_action_data(step, index: int) -> dict:
    return {
        "name": _workflow_step_display_name(step, index),
        "action": step.action,
        "locator_type": step.locator_type,
        "locator_value": step.locator_value,
        "extra_value": step.extra_value,
    }


def _build_workflow_summary(args, workflow, **extra_fields) -> dict:
    summary = {
        "workflow_path": str(Path(args.workflow).resolve()),
        "workflow_name": workflow.name or Path(args.workflow).stem,
        "workflow_platform": workflow.platform or args.platform,
        "resolved_vars": dict(workflow.vars),
        "step_count": len([step for step in workflow.steps if step.enabled]),
    }
    summary.update(extra_fields)
    return summary


def _resolve_control_identity(args, execution_mode: str) -> dict:
    if execution_mode == MODE_DOCTOR:
        return {
            "control_kind": "doctor",
            "control_label": "doctor",
            "control_source_ref": "",
        }

    workflow_path = str(getattr(args, "workflow", "")).strip()
    if workflow_path:
        workflow_file = Path(workflow_path).expanduser().resolve()
        return {
            "control_kind": "workflow",
            "control_label": workflow_file.stem,
            "control_source_ref": str(workflow_file),
        }

    action = str(getattr(args, "action", "")).strip()
    if action:
        return {
            "control_kind": "action",
            "control_label": str(getattr(args, "action_name", "")).strip() or action,
            "control_source_ref": "inline://action",
        }

    return {
        "control_kind": "goal",
        "control_label": str(getattr(args, "goal", "")).strip(),
        "control_source_ref": str(getattr(args, "context", "")).strip(),
    }


def _build_inline_action_data(args) -> dict:
    locator_type = str(getattr(args, "locator_type", "")).strip() or "global"
    locator_value = str(getattr(args, "locator_value", "")).strip() or "global"
    extra_value = str(getattr(args, "extra_value", ""))
    action_name = str(getattr(args, "action_name", "")).strip()
    if not action_name:
        if locator_value.lower() != "global":
            action_name = f"{args.action}:{locator_value}"
        elif extra_value:
            action_name = f"{args.action}:{extra_value}"
        else:
            action_name = str(args.action).strip()

    return {
        "name": action_name,
        "action": str(args.action).strip(),
        "locator_type": locator_type,
        "locator_value": locator_value,
        "extra_value": extra_value,
    }


def _build_action_summary(args, action_data: dict, **extra_fields) -> dict:
    summary = {
        "action_name": action_data.get("name", ""),
        "action": action_data.get("action", ""),
        "locator_type": action_data.get("locator_type", ""),
        "locator_value": action_data.get("locator_value", ""),
        "extra_value": action_data.get("extra_value", ""),
    }
    summary.update(extra_fields)
    return summary


def _resolve_output_script_path(args) -> str:
    if args.output:
        output_script_path = args.output
    else:
        base_dir = os.path.abspath(os.path.dirname(__file__))
        platform_dir = os.path.join(base_dir, "test_cases", args.platform)
        os.makedirs(platform_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_script_path = os.path.join(
            platform_dir, f"test_auto_agent_{timestamp}.py"
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_script_path)), exist_ok=True)
    return output_script_path


def _format_resume_context(resume_context: dict) -> str:
    actions = resume_context.get("successful_actions", [])
    actions_str = "；".join(actions) if actions else "无"
    screenshot_path = resume_context.get("latest_screenshot_path", "") or "无"
    control_summary = resume_context.get("control_summary", {}) or {}
    failure_analysis = resume_context.get("failure_analysis", {}) or {}
    pytest_asset = resume_context.get("pytest_asset", {}) or {}
    control_kind = control_summary.get("control_kind", "") or "unknown"
    control_label = control_summary.get("control_label", "") or resume_context.get("goal", "")
    source_ref = control_summary.get("source_ref", "") or "无"
    failure_category = failure_analysis.get("category", "") or "无"
    failure_stage = failure_analysis.get("stage", "") or "无"
    failure_summary = failure_analysis.get("summary", "") or "无"
    failure_retryable = failure_analysis.get("retryable", "无")
    failure_recommended_command = failure_analysis.get("recommended_command", "") or "无"
    recovery_hint = failure_analysis.get("recovery_hint", "") or "无"
    pytest_target = pytest_asset.get("pytest_target", "") or "无"
    pytest_command = pytest_asset.get("pytest_command", "") or "无"
    pytest_manifest_path = pytest_asset.get("manifest_path", "") or "无"
    resume_commands = pytest_asset.get("resume_commands", {}) or {}
    resume_dry_run_command = resume_commands.get("dry_run", "") or "无"
    return (
        "\n【上次运行恢复上下文】:\n"
        f"- run_id: {resume_context.get('run_id', '')}\n"
        f"- control_kind: {control_kind}\n"
        f"- control_label: {control_label}\n"
        f"- source_ref: {source_ref}\n"
        f"- goal: {resume_context.get('goal', '')}\n"
        f"- platform: {resume_context.get('platform', '')}\n"
        f"- env: {resume_context.get('env', '')}\n"
        f"- status: {resume_context.get('status', '')}\n"
        f"- successful_actions: {actions_str}\n"
        f"- last_error: {resume_context.get('last_error', '')}\n"
        f"- failure_category: {failure_category}\n"
        f"- failure_stage: {failure_stage}\n"
        f"- failure_summary: {failure_summary}\n"
        f"- failure_retryable: {failure_retryable}\n"
        f"- failure_recommended_command: {failure_recommended_command}\n"
        f"- recovery_hint: {recovery_hint}\n"
        f"- pytest_target: {pytest_target}\n"
        f"- pytest_command: {pytest_command}\n"
        f"- pytest_manifest_path: {pytest_manifest_path}\n"
        f"- resume_dry_run_command: {resume_dry_run_command}\n"
        f"- latest_screenshot_path: {screenshot_path}\n"
    )


def _load_context_content(args):
    context_content = ""
    if args.context and os.path.exists(args.context):
        with open(args.context, "r", encoding="utf-8") as f:
            context_content = f.read()
        log.info(f"📄 已成功加载业务上下文文件: {args.context}")

    resume_context = {}
    if args.resume_run_id:
        run_dir = Path(config.RUN_REPORT_BASE_DIR) / args.resume_run_id
        resume_context = load_run_context(run_dir)
        context_content = f"{context_content}{_format_resume_context(resume_context)}"
        log.info(f"🧩 已从 run_id={args.resume_run_id} 恢复最小上下文")

    return context_content, resume_context


def _build_reporter(args, output_script_path: str, execution_mode: str) -> RunReporter:
    _ensure_reporter_class()
    control_identity = _resolve_control_identity(args, execution_mode)
    goal_label = control_identity["control_label"] or f"{args.platform} {execution_mode}"
    return RunReporter(
        goal=goal_label,
        platform=args.platform,
        env_name=args.env,
        output_script_path=output_script_path,
        json_output=args.json,
        vision_enabled=args.vision,
        max_steps=args.max_steps,
        execution_mode=execution_mode,
        resume_from_run_id=args.resume_run_id,
        control_kind=control_identity["control_kind"],
        control_label=control_identity["control_label"],
        control_source_ref=control_identity["control_source_ref"],
    )


def _emit_run_started(
    reporter: RunReporter, args, output_script_path: str, execution_mode: str
) -> None:
    control_identity = _resolve_control_identity(args, execution_mode)
    reporter.emit_event(
        "run_started",
        goal=control_identity["control_label"],
        platform=args.platform,
        env=args.env,
        output_script_path=output_script_path,
        vision_enabled=args.vision,
        execution_mode=execution_mode,
        resume_run_id=args.resume_run_id,
        control_kind=control_identity["control_kind"],
        control_label=control_identity["control_label"],
        control_source_ref=control_identity["control_source_ref"],
    )


def _apply_resume_summary(reporter: RunReporter, resume_context: dict) -> None:
    reporter.update_summary(
        resume_context_available=bool(resume_context),
    )
    if resume_context:
        reporter.update_control_summary(
            resume_context=resume_context.get("control_summary", {}) or {},
        )


def _wait_for_platform_idle(platform: str, device) -> None:
    try:
        if platform == "android":
            device.wait_activity(device.app_current()["activity"], timeout=3)
        elif platform == "web":
            device.wait_for_load_state("domcontentloaded")
    except Exception:
        time.sleep(1)


def _capture_ui_state(args, adapter, reporter: RunReporter, step_index: int):
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


def _connect_adapter(args, reporter: RunReporter):
    adapter = _create_adapter(args.platform)
    adapter.setup()
    device = adapter.driver
    log.info(f"✅ {args.platform} 平台已连接并初始化完成")
    launch_app(device, args.env, args.platform)
    reporter.emit_event("adapter_ready", platform=args.platform)
    return adapter


def _preview_action_resolution(device, platform: str, action_data: dict) -> dict:
    _ensure_executor_runtime()
    l_type = action_data.get("locator_type", "")
    l_value = action_data.get("locator_value", "")
    if not l_type or str(l_type).lower() == "global" or str(l_value).lower() == "global":
        return {"resolvable": True, "resolution_error": ""}

    u2_locator_map = {
        "resourceId": "resourceId",
        "text": "text",
        "description": "description",
        "id": "resourceId",
    }
    u2_key = u2_locator_map.get(l_type, l_type)
    try:
        element = get_actual_element(device, platform, u2_key, l_value)
        return {"resolvable": element is not None, "resolution_error": ""}
    except Exception as e:
        return {"resolvable": False, "resolution_error": str(e)}


def _build_resolution_hint(args, action_data: dict, resolution: dict) -> str:
    if resolution.get("resolvable", False):
        return ""

    locator_type = action_data.get("locator_type", "")
    if not args.vision and str(locator_type).lower() != "global":
        return "定位解析失败，建议先确认当前页面状态，必要时重试并开启 --vision。"
    return "定位解析失败，建议先确认当前页面结构、上下文约束和目标元素是否真实存在。"


def _normalize_doctor_message(message: str) -> str:
    lines = [line.strip() for line in str(message).splitlines() if line.strip()]
    return lines[0] if lines else ""


def _iter_doctor_check_findings(check: dict):
    for issue in check.get("issues", []) or []:
        text = _normalize_doctor_message(issue)
        if text:
            yield "issue", text

    for error in check.get("errors", []) or []:
        text = _normalize_doctor_message(error)
        if text:
            yield "error", text

    error_text = _normalize_doctor_message(check.get("error", ""))
    if error_text:
        yield "error", error_text

    hint_text = _normalize_doctor_message(check.get("hint", ""))
    if hint_text:
        yield "hint", hint_text


def _classify_doctor_check(check: dict) -> dict:
    check_name = str(check.get("name", "")).strip()

    if check_name == "config":
        return {"category": "config", "title": "配置问题", "priority": 1}
    if check_name in {"venv_consistency", "runtime_paths"}:
        return {"category": "runtime", "title": "运行时问题", "priority": 2}
    if check_name in {"adb", "uiautomator2", "wda", "playwright"}:
        return {"category": "dependency", "title": "依赖问题", "priority": 3}
    if check_name in {
        "adb_devices",
        "wda_status",
        "cdp_debug_endpoint",
        "http://localhost:8100",
        "http://localhost:9222",
    } or check_name.startswith(("http://", "https://")):
        return {"category": "connectivity", "title": "连接问题", "priority": 4}
    return {"category": "other", "title": "其他问题", "priority": 5}


def _doctor_fix_doc_reference(doc_name: str, section: str) -> dict:
    project_root = Path(__file__).resolve().parent
    doc_path = project_root / doc_name
    return {
        "fix_doc": str(doc_path),
        "fix_doc_section": section,
    }


def _build_doctor_remediation(check_name: str, message: str) -> dict:
    message = str(message).strip()
    normalized_check_name = str(check_name).strip()
    common_doc = _doctor_fix_doc_reference(
        "README_CLI.md", "Doctor 快速修复 / 通用"
    )

    remediation = {
        "fix_label": "查看诊断文档",
        "fix_command": "",
        **common_doc,
    }

    if normalized_check_name == "config":
        return {
            "fix_label": "补齐运行配置",
            "fix_command": "",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / 配置"),
        }

    if normalized_check_name == "venv_consistency":
        return {
            "fix_label": "修复虚拟环境入口漂移",
            "fix_command": "./.venv/bin/python scripts/repair_venv.py",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / 运行环境"),
        }

    if normalized_check_name == "runtime_paths":
        return {
            "fix_label": "确认运行目录可写",
            "fix_command": "",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / 运行环境"),
        }

    if normalized_check_name == "uiautomator2":
        return {
            "fix_label": "补齐 Android Python 依赖",
            "fix_command": "./.venv/bin/python -m pip install -r requirement.txt",
            **_doctor_fix_doc_reference("README.md", "安装 Python 依赖库"),
        }

    if normalized_check_name == "playwright":
        return {
            "fix_label": "安装 Playwright 依赖",
            "fix_command": "./.venv/bin/python -m pip install playwright",
            **_doctor_fix_doc_reference("README.md", "安装 Python 依赖库"),
        }

    if normalized_check_name == "wda":
        return {
            "fix_label": "安装 iOS WDA 依赖",
            "fix_command": "./.venv/bin/python -m pip install facebook-wda",
            **_doctor_fix_doc_reference("README.md", "安装 Python 依赖库"),
        }

    if normalized_check_name == "adb":
        return {
            "fix_label": "安装并暴露 adb 到 PATH",
            "fix_command": "",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / Android"),
        }

    if normalized_check_name == "adb_devices":
        if "当前运行环境限制了" in message or "宿主终端" in message:
            return {
                "fix_label": "在宿主终端重试 adb 检查",
                "fix_command": "adb devices",
                **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / Android"),
            }
        return {
            "fix_label": "检查 Android 设备连接状态",
            "fix_command": "adb devices",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / Android"),
        }

    if normalized_check_name in {"http://localhost:8100", "wda_status"}:
        return {
            "fix_label": "确认 WebDriverAgent 服务状态",
            "fix_command": "",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / iOS"),
        }

    if normalized_check_name in {"http://localhost:9222", "cdp_debug_endpoint"}:
        if "当前运行环境限制了" in message or "宿主终端" in message:
            return {
                "fix_label": "在宿主终端检查 Chrome DevTools 调试端口",
                "fix_command": "curl -sS http://localhost:9222/json/version",
                **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / Web"),
            }
        return {
            "fix_label": "确认 Chrome DevTools 调试端口",
            "fix_command": "",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / Web"),
        }

    if "OPENAI_API_KEY" in message or "WEB_CDP_URL" in message:
        return {
            "fix_label": "补齐运行配置",
            "fix_command": "",
            **_doctor_fix_doc_reference("README_CLI.md", "Doctor 快速修复 / 配置"),
        }

    return remediation


def _doctor_action_signature(category: str, item: dict) -> tuple:
    return (
        category,
        tuple(item.get("check_names", [])),
        item.get("fix_label", ""),
        item.get("fix_command", ""),
        item.get("fix_doc", ""),
        item.get("fix_doc_section", ""),
    )


def _append_recommended_action(actions: list[dict], category: str, priority: int, item: dict) -> None:
    candidate = {
        "category": category,
        "priority": priority,
        **item,
    }
    candidate_signature = _doctor_action_signature(category, item)

    for index, existing in enumerate(actions):
        existing_signature = _doctor_action_signature(existing.get("category", ""), existing)
        if existing_signature != candidate_signature:
            continue

        if candidate.get("kind") == "hint":
            actions[index] = candidate
            return

        if existing.get("kind") == "hint":
            return

    actions.append(candidate)


def _build_doctor_summary(checks: list[dict]) -> dict:
    groups = {}
    severity_rank = {"error": 0, "issue": 1, "hint": 2}

    for check in checks:
        if check.get("ok", False):
            continue

        group_meta = _classify_doctor_check(check)
        category = group_meta["category"]
        group = groups.setdefault(
            category,
            {
                "category": category,
                "title": group_meta["title"],
                "priority": group_meta["priority"],
                "items": [],
                "_item_map": {},
            },
        )

        check_name = str(check.get("name", "unknown")).strip() or "unknown"
        for kind, message in _iter_doctor_check_findings(check):
            remediation = _build_doctor_remediation(check_name, message)
            existing = group["_item_map"].get(message)
            if existing:
                if check_name not in existing["check_names"]:
                    existing["check_names"].append(check_name)
                if severity_rank[kind] < severity_rank[existing["kind"]]:
                    existing["kind"] = kind
                if not existing["fix_command"] and remediation.get("fix_command", ""):
                    existing["fix_command"] = remediation.get("fix_command", "")
                if existing.get("fix_doc_section", "") == "Doctor 快速修复 / 通用":
                    existing["fix_label"] = remediation.get("fix_label", existing["fix_label"])
                    existing["fix_doc"] = remediation.get("fix_doc", existing["fix_doc"])
                    existing["fix_doc_section"] = remediation.get(
                        "fix_doc_section", existing["fix_doc_section"]
                    )
                continue

            item = {
                "message": message,
                "kind": kind,
                "check_names": [check_name],
                "fix_label": remediation.get("fix_label", ""),
                "fix_command": remediation.get("fix_command", ""),
                "fix_doc": remediation.get("fix_doc", ""),
                "fix_doc_section": remediation.get("fix_doc_section", ""),
                "fix_priority": group["priority"],
            }
            group["_item_map"][message] = item
            group["items"].append(item)

    ordered_groups = sorted(
        groups.values(),
        key=lambda item: (item["priority"], item["category"]),
    )
    for group in ordered_groups:
        group.pop("_item_map", None)

    top_items = []
    recommended_actions = []
    for group in ordered_groups:
        for item in group["items"]:
            top_items.append(item["message"])
            _append_recommended_action(
                recommended_actions,
                group["category"],
                group["priority"],
                item,
            )

    return {
        "ok": not ordered_groups,
        "group_count": len(ordered_groups),
        "top_items": top_items,
        "groups": ordered_groups,
        "recommended_actions": recommended_actions,
    }


def _build_doctor_remediation_items(checks: list[dict]) -> list[str]:
    return _build_doctor_summary(checks).get("top_items", [])


def _build_doctor_check_failure_message(check: dict) -> str:
    details = []

    def add_detail(message: str) -> None:
        text = _normalize_doctor_message(message)
        if text and text not in details:
            details.append(text)

    for issue in check.get("issues", []) or []:
        add_detail(issue)

    for error in check.get("errors", []) or []:
        add_detail(error)

    add_detail(check.get("error", ""))

    if not details:
        if "path" in check and not str(check.get("path", "")).strip():
            details.append("未找到可执行文件")
        elif check.get("name") == "runtime_paths":
            details.append("运行时目录不可用或不可写")
        else:
            details.append("检查未通过")

    return f"   - {check.get('name', 'unknown')}: {'；'.join(details)}"


def run_doctor_mode(args, output_script_path: str) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_DOCTOR)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    _emit_run_started(reporter, args, output_script_path, MODE_DOCTOR)

    try:
        _ensure_preflight_runner()
        result = run_preflight(
            platform=args.platform,
            script_dir=Path(os.path.dirname(os.path.abspath(output_script_path))),
            run_dir=Path(config.RUN_REPORT_BASE_DIR),
        )
        for check in result.get("checks", []):
            reporter.emit_event(
                "doctor_check",
                check_name=check.get("name", ""),
                success=check.get("ok", False),
                detail=check,
            )
        doctor_summary = _build_doctor_summary(result.get("checks", []))
        reporter.update_summary(doctor_summary=doctor_summary)
        reporter.emit_event(
            "doctor_summary",
            ok=doctor_summary.get("ok", False),
            group_count=doctor_summary.get("group_count", 0),
            top_items=doctor_summary.get("top_items", []),
            groups=doctor_summary.get("groups", []),
            recommended_actions=doctor_summary.get("recommended_actions", []),
        )

        if result.get("ok"):
            log.info("🩺 [Doctor] 环境体检通过，可以继续执行。")
            final_status = "success"
            exit_code = 0
        else:
            final_error = "doctor 检查未通过"
            log.error("❌ [Doctor] 环境体检未通过，请先修复前置条件。")
            for check in result.get("checks", []):
                if not check.get("ok", False):
                    log.error(_build_doctor_check_failure_message(check))
            remediation_items = doctor_summary.get("recommended_actions", [])
            if remediation_items:
                log.error("🧭 [Doctor] 建议优先处理以下问题：")
                for index, item in enumerate(remediation_items, start=1):
                    log.error(f"   {index}. {item.get('message', '')}")
                    if item.get("fix_command"):
                        log.error(f"      命令: {item.get('fix_command', '')}")
                    if item.get("fix_doc"):
                        log.error(
                            "      文档: "
                            f"{item.get('fix_doc', '')} ({item.get('fix_doc_section', '')})"
                        )
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=len(result.get("checks", [])) if "result" in locals() else 0,
            last_error=final_error,
        )
    return exit_code


def run_capabilities_mode(args) -> int:
    payload = get_capabilities_payload()
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    return 0


def _dispatch_execution(
    args,
    execution_mode: str,
    output_script_path: str,
    context_content: str,
    resume_context: dict,
) -> int:
    if execution_mode == MODE_DOCTOR:
        return run_doctor_mode(args, output_script_path)
    if args.workflow and execution_mode == MODE_PLAN_ONLY:
        return run_workflow_plan_only_mode(
            args,
            output_script_path,
            resume_context,
        )
    if args.workflow and execution_mode == MODE_DRY_RUN:
        return run_workflow_dry_run_mode(
            args,
            output_script_path,
            resume_context,
        )
    if args.workflow:
        return run_workflow_default_mode(
            args,
            output_script_path,
            resume_context,
        )
    if args.action and execution_mode == MODE_PLAN_ONLY:
        return run_action_plan_only_mode(
            args,
            output_script_path,
            resume_context,
        )
    if args.action and execution_mode == MODE_DRY_RUN:
        return run_action_dry_run_mode(
            args,
            output_script_path,
            resume_context,
        )
    if args.action:
        return run_action_default_mode(
            args,
            output_script_path,
            resume_context,
        )
    if execution_mode == MODE_PLAN_ONLY:
        return run_plan_only_mode(
            args,
            output_script_path,
            context_content,
            resume_context,
        )
    if execution_mode == MODE_DRY_RUN:
        return run_dry_run_mode(
            args,
            output_script_path,
            context_content,
            resume_context,
        )
    return run_default_mode(
        args,
        output_script_path,
        context_content,
        resume_context,
    )


def _list_run_dirs(base_dir: Path) -> set[Path]:
    if not base_dir.exists():
        return set()
    return {item for item in base_dir.iterdir() if item.is_dir()}


def _resolve_new_run_dir(before: set[Path], base_dir: Path) -> Path | None:
    after = _list_run_dirs(base_dir)
    new_dirs = sorted(after - before)
    if new_dirs:
        return new_dirs[-1]
    if not after:
        return None
    return sorted(after)[-1]


def _emit_tool_response(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    return int(payload.get("exit_code", 0))


def _empty_run_assets() -> dict:
    return {
        "summary_path": "",
        "artifacts_path": "",
        "pytest_replay_path": "",
        "failure_analysis": {},
        "pytest_asset": {},
        "resume_commands": {},
        "recommended_next_step": None,
    }


def _load_run_assets(run_dir: Path | None) -> dict:
    if not run_dir:
        return {
            "summary": {},
            "run_assets": _empty_run_assets(),
            "resume_context": {},
        }

    bundle = load_run_bundle(run_dir)
    return {
        "summary": bundle.get("summary", {}) or {},
        "run_assets": bundle.get("run_assets", {}) or _empty_run_assets(),
        "resume_context": bundle.get("resume_context", {}) or {},
    }


def build_tool_response_payload(request) -> dict:
    if request.operation == "capabilities":
        payload = build_capabilities_response()
        payload["exit_code"] = 0
        return payload
    if request.operation == "load_run":
        return build_load_run_payload(request.run_id)

    parser = build_parser()
    request_args = parser.parse_args([])
    for key, value in build_cli_arg_overrides(request).items():
        setattr(request_args, key, value)

    try:
        validate_cli_args(request_args)
    except ValueError as e:
        return {
            "ok": False,
            "operation": "execute",
            "exit_code": 2,
            "error": str(e),
        }

    execution_mode = resolve_execution_mode(
        doctor=request_args.doctor,
        plan_only=request_args.plan_only,
        dry_run=request_args.dry_run,
    )
    output_script_path = _resolve_output_script_path(request_args)
    run_base_dir = Path(config.RUN_REPORT_BASE_DIR)
    previous_run_dirs = _list_run_dirs(run_base_dir)

    try:
        context_content, resume_context = _load_context_content(request_args)
    except RunContextLoadError as e:
        return {
            "ok": False,
            "operation": "execute",
            "exit_code": 2,
            "mode": execution_mode,
            "error": str(e),
        }

    if execution_mode != MODE_DOCTOR and not config.validate_config():
        return {
            "ok": False,
            "operation": "execute",
            "exit_code": 1,
            "mode": execution_mode,
            "error": "配置校验失败",
        }

    mute_logs_context = nullcontext
    try:
        from common.logs import mute_stderr_logs as _mute_stderr_logs

        mute_logs_context = _mute_stderr_logs
    except Exception:
        mute_logs_context = nullcontext

    with mute_logs_context():
        exit_code = _dispatch_execution(
            request_args,
            execution_mode,
            output_script_path,
            context_content,
            resume_context,
        )
    run_dir = _resolve_new_run_dir(previous_run_dirs, run_base_dir)
    loaded_assets = _load_run_assets(run_dir) if run_dir and (run_dir / "summary.json").exists() else {
        "summary": {},
        "run_assets": _empty_run_assets(),
        "resume_context": {},
    }
    summary = loaded_assets["summary"]
    run_assets = loaded_assets["run_assets"]
    summary_path = run_assets.get("summary_path", "")

    return {
        "ok": exit_code == 0,
        "operation": "execute",
        "mode": execution_mode,
        "exit_code": exit_code,
        "run_dir": str(run_dir) if run_dir else "",
        "summary_path": summary_path,
        "summary": summary,
        "run_assets": run_assets,
        "recommended_next_step": run_assets.get("recommended_next_step"),
    }


def build_load_run_payload(run_id: str) -> dict:
    run_id = str(run_id).strip()
    run_dir = Path(config.RUN_REPORT_BASE_DIR) / run_id
    try:
        bundle = load_run_bundle(run_dir)
    except RunContextLoadError as e:
        return {
            "ok": False,
            "operation": "load_run",
            "exit_code": 2,
            "run_id": run_id,
            "error": str(e),
            "run_assets": _empty_run_assets(),
        }

    run_assets = bundle.get("run_assets", {}) or _empty_run_assets()
    return {
        "ok": True,
        "operation": "load_run",
        "exit_code": 0,
        "run_id": bundle.get("run_id", "") or run_id,
        "run_dir": bundle.get("run_dir", str(run_dir)),
        "summary_path": run_assets.get("summary_path", ""),
        "summary": bundle.get("summary", {}) or {},
        "run_assets": run_assets,
        "recommended_next_step": run_assets.get("recommended_next_step"),
        "resume_context": bundle.get("resume_context", {}) or {},
    }


def _run_tool_request(request) -> int:
    return _emit_tool_response(build_tool_response_payload(request))


def run_tool_request_mode(args) -> int:
    try:
        request = load_tool_request(args.tool_request)
    except ToolRequestError as e:
        return _emit_tool_response(
            {
                "ok": False,
                "operation": "tool_request",
                "exit_code": 2,
                "error": str(e),
            }
        )
    return _run_tool_request(request)


def run_tool_stdin_mode(args) -> int:
    try:
        request = load_tool_request_from_stdin(sys.stdin.read())
    except ToolRequestError as e:
        return _emit_tool_response(
            {
                "ok": False,
                "operation": "tool_stdin",
                "exit_code": 2,
                "error": str(e),
            }
        )
    return _run_tool_request(request)


def run_mcp_server_mode(args) -> int:
    from common.mcp_server import run_stdio_mcp_server

    return run_stdio_mcp_server(build_tool_response_payload, build_load_run_payload)


def run_plan_only_mode(
    args,
    output_script_path: str,
    context_content: str,
    resume_context: dict,
) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_PLAN_ONLY)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    adapter = None
    steps_executed = 0
    _emit_run_started(reporter, args, output_script_path, MODE_PLAN_ONLY)
    _apply_resume_summary(reporter, resume_context)

    try:
        adapter = _connect_adapter(args, reporter)
        ui_json, screenshot_base64 = _capture_ui_state(args, adapter, reporter, 1)
        _ensure_runtime_classes()
        brain = AutonomousBrain()
        plan = brain.get_execution_plan(
            goal=args.goal,
            context=context_content,
            ui_json=ui_json,
            history=[],
            platform=args.platform,
            screenshot_base64=screenshot_base64,
        )

        planned_steps = plan.get("planned_steps", [])
        steps_executed = len(planned_steps) or 1
        reporter.emit_event(
            "plan_generated",
            current_state_summary=plan.get("current_state_summary", ""),
            planned_steps=planned_steps,
            suggested_assertion=plan.get("suggested_assertion", ""),
            risks=plan.get("risks", []),
        )
        reporter.update_summary(plan_preview=plan)
        log.info(f"🧭 [Plan] 当前页面摘要: {plan.get('current_state_summary', '')}")
        for index, step in enumerate(planned_steps, start=1):
            log.info(f"🧭 [Plan] 步骤 {index}: {step}")
        if plan.get("suggested_assertion"):
            log.info(f"🧭 [Plan] 建议断言: {plan.get('suggested_assertion', '')}")

        final_status = "success"
        exit_code = 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("plan_failed", error=str(e))
        log.error(f"❌ [Plan] 计划生成失败: {e}")
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=final_error,
        )
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")
    return exit_code


def run_workflow_plan_only_mode(
    args,
    output_script_path: str,
    resume_context: dict,
) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_PLAN_ONLY)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    _emit_run_started(reporter, args, output_script_path, MODE_PLAN_ONLY)
    _apply_resume_summary(reporter, resume_context)

    try:
        workflow = _load_workflow_definition(args)
        planned_steps = [
            _workflow_step_display_name(step, index)
            for index, step in enumerate(workflow.steps, start=1)
            if step.enabled
        ]
        plan = {
            "current_state_summary": f"工作流 [{workflow.name or Path(args.workflow).stem}] 预览",
            "planned_steps": planned_steps,
            "suggested_assertion": "",
            "risks": [],
        }
        workflow_summary = _build_workflow_summary(args, workflow)
        reporter.update_control_summary(
            control_kind="workflow",
            control_label=workflow_summary["workflow_name"],
            source_ref=workflow_summary["workflow_path"],
            step_count=workflow_summary["step_count"],
            resolved_vars=workflow_summary["resolved_vars"],
        )
        reporter.emit_event(
            "workflow_loaded",
            workflow_name=workflow_summary["workflow_name"],
            workflow_path=workflow_summary["workflow_path"],
            step_count=workflow_summary["step_count"],
        )
        reporter.emit_event(
            "plan_generated",
            current_state_summary=plan["current_state_summary"],
            planned_steps=planned_steps,
            suggested_assertion="",
            risks=[],
        )
        reporter.update_summary(plan_preview=plan, workflow_summary=workflow_summary)

        log.info(f"🧭 [Workflow] 工作流名称: {workflow_summary['workflow_name']}")
        for index, step_name in enumerate(planned_steps, start=1):
            log.info(f"🧭 [Workflow] 步骤 {index}: {step_name}")

        final_status = "success"
        exit_code = 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("workflow_plan_failed", error=str(e))
        log.error(f"❌ [Workflow] 计划生成失败: {e}")
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=0 if final_error else 1,
            last_error=final_error,
        )
    return exit_code


def run_dry_run_mode(
    args,
    output_script_path: str,
    context_content: str,
    resume_context: dict,
) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_DRY_RUN)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    adapter = None
    _emit_run_started(reporter, args, output_script_path, MODE_DRY_RUN)
    _apply_resume_summary(reporter, resume_context)

    try:
        adapter = _connect_adapter(args, reporter)
        ui_json, screenshot_base64 = _capture_ui_state(args, adapter, reporter, 1)
        _ensure_runtime_classes()
        brain = AutonomousBrain()
        decision_data = brain.get_next_autonomous_action(
            goal=args.goal,
            context=context_content,
            ui_json=ui_json,
            history=[],
            platform=args.platform,
            last_error="",
            screenshot_base64=screenshot_base64,
        )

        status = decision_data.get("status", "failed")
        action_data = decision_data.get("result", {})
        resolution = _preview_action_resolution(
            adapter.driver, args.platform, action_data
        )
        resolution_hint = _build_resolution_hint(args, action_data, resolution)
        reporter.emit_event(
            "dry_run_preview",
            status=status,
            action=action_data.get("action", ""),
            locator_type=action_data.get("locator_type", ""),
            locator_value=action_data.get("locator_value", ""),
            extra_value=action_data.get("extra_value", ""),
            resolvable=resolution.get("resolvable", False),
            resolution_error=resolution.get("resolution_error", ""),
            resolution_hint=resolution_hint,
        )
        reporter.update_summary(
            dry_run_preview={
                "status": status,
                "action": action_data.get("action", ""),
                "locator_type": action_data.get("locator_type", ""),
                "locator_value": action_data.get("locator_value", ""),
                "extra_value": action_data.get("extra_value", ""),
                "resolvable": resolution.get("resolvable", False),
                "resolution_error": resolution.get("resolution_error", ""),
                "resolution_hint": resolution_hint,
            }
        )

        if status == "failed":
            final_error = "任务无法继续，AI 主动判断为失败"
            log.warning("⚠️ [Dry Run] AI 判断当前任务无法继续。")
            exit_code = 1
        else:
            log.info(
                f"🧪 [Dry Run] would_execute: {action_data.get('action', '')} "
                f"{action_data.get('locator_type', '')}={action_data.get('locator_value', '')}"
            )
            final_status = "success"
            exit_code = 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("dry_run_failed", error=str(e))
        log.error(f"❌ [Dry Run] 模拟执行失败: {e}")
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=1 if not final_error else 0,
            last_error=final_error,
        )
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")
    return exit_code


def run_workflow_dry_run_mode(
    args,
    output_script_path: str,
    resume_context: dict,
) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_DRY_RUN)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    adapter = None
    preview_steps = []
    _emit_run_started(reporter, args, output_script_path, MODE_DRY_RUN)
    _apply_resume_summary(reporter, resume_context)

    try:
        workflow = _load_workflow_definition(args)
        workflow_summary = _build_workflow_summary(args, workflow)
        reporter.update_control_summary(
            control_kind="workflow",
            control_label=workflow_summary["workflow_name"],
            source_ref=workflow_summary["workflow_path"],
            step_count=workflow_summary["step_count"],
            resolved_vars=workflow_summary["resolved_vars"],
        )
        reporter.emit_event(
            "workflow_loaded",
            workflow_name=workflow_summary["workflow_name"],
            workflow_path=workflow_summary["workflow_path"],
            step_count=workflow_summary["step_count"],
        )

        adapter = _connect_adapter(args, reporter)
        unresolved_steps = 0
        for index, step in enumerate(workflow.steps, start=1):
            if not step.enabled:
                continue

            action_data = _workflow_step_to_action_data(step, index)
            resolution = _preview_action_resolution(
                adapter.driver, args.platform, action_data
            )
            resolution_hint = _build_resolution_hint(args, action_data, resolution)
            preview = {
                "step": index,
                "name": action_data["name"],
                "action": action_data["action"],
                "locator_type": action_data["locator_type"],
                "locator_value": action_data["locator_value"],
                "extra_value": action_data["extra_value"],
                "resolvable": resolution.get("resolvable", False),
                "resolution_error": resolution.get("resolution_error", ""),
                "resolution_hint": resolution_hint,
            }
            if not preview["resolvable"]:
                unresolved_steps += 1
            preview_steps.append(preview)
            reporter.emit_event("workflow_step_preview", **preview)

        workflow_summary = _build_workflow_summary(
            args,
            workflow,
            preview_steps=preview_steps,
            unresolved_steps=unresolved_steps,
        )
        reporter.update_control_summary(
            preview_steps=preview_steps,
            unresolved_steps=unresolved_steps,
        )
        reporter.update_summary(
            workflow_summary=workflow_summary,
            dry_run_preview={
                "workflow": True,
                "step_count": workflow_summary["step_count"],
                "unresolved_steps": unresolved_steps,
                "preview_steps": preview_steps,
            },
        )

        if unresolved_steps:
            final_error = f"存在 {unresolved_steps} 个 workflow 步骤无法解析"
            exit_code = 1
        else:
            final_status = "success"
            exit_code = 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("workflow_dry_run_failed", error=str(e))
        log.error(f"❌ [Workflow] 模拟执行失败: {e}")
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=len(preview_steps),
            last_error=final_error,
        )
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")
    return exit_code


def run_workflow_default_mode(
    args,
    output_script_path: str,
    resume_context: dict,
) -> int:
    adapter = None
    reporter = _build_reporter(args, output_script_path, MODE_RUN)
    exit_code = 1
    final_status = "failed"
    final_error = ""
    steps_executed = 0
    _emit_run_started(reporter, args, output_script_path, MODE_RUN)
    _apply_resume_summary(reporter, resume_context)

    try:
        workflow = _load_workflow_definition(args)
        workflow_summary = _build_workflow_summary(
            args, workflow, executed_steps=0
        )
        reporter.update_control_summary(
            control_kind="workflow",
            control_label=workflow_summary["workflow_name"],
            source_ref=workflow_summary["workflow_path"],
            step_count=workflow_summary["step_count"],
            resolved_vars=workflow_summary["resolved_vars"],
        )
        reporter.emit_event(
            "workflow_loaded",
            workflow_name=workflow_summary["workflow_name"],
            workflow_path=workflow_summary["workflow_path"],
            step_count=workflow_summary["step_count"],
        )

        try:
            adapter = _connect_adapter(args, reporter)
            device = adapter.driver
        except Exception as e:
            final_error = str(e)
            reporter.emit_event("startup_failed", platform=args.platform, error=str(e))
            log.error(f"❌ [Error]{args.platform} 连接失败: {e}")
            return 1

        _ensure_history_manager()
        _ensure_executor_runtime()
        history_manager = StepHistoryManager(initial_content=get_initial_header())
        save_to_disk(output_script_path, get_initial_header())
        executor = UIExecutor(device, platform=args.platform)

        executed_steps = 0
        for index, step in enumerate(workflow.steps, start=1):
            if not step.enabled:
                continue

            steps_executed = index
            action_data = _workflow_step_to_action_data(step, index)
            reporter.emit_event(
                "step_started",
                step=index,
                source="workflow",
                step_name=action_data["name"],
            )
            result = executor.execute_and_record(action_data)
            if not result.get("success"):
                final_error = f"workflow 步骤执行失败: {action_data['name']}"
                reporter.emit_event(
                    "action_executed",
                    step=index,
                    success=False,
                    action_description=action_data["name"],
                )
                log.error(f"❌ [Workflow] 步骤执行失败: {action_data['name']}")
                return 1

            history_manager.add_step(
                result["code_lines"], result["action_description"]
            )
            save_to_disk(output_script_path, history_manager.get_current_file_content())
            reporter.emit_event(
                "action_executed",
                step=index,
                success=True,
                action_description=result["action_description"],
            )
            executed_steps += 1

        reporter.update_summary(
            workflow_summary=_build_workflow_summary(
                args, workflow, executed_steps=executed_steps
            )
        )
        reporter.update_control_summary(executed_steps=executed_steps)
        final_status = "success"
        exit_code = 0
        return 0

    except Exception as e:
        final_error = str(e)
        reporter.emit_event("workflow_run_failed", error=str(e))
        log.error(f"❌ [Workflow] 执行失败: {e}")
        return 1

    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=final_error,
        )
        log.info(f"🏁 任务结束，当前已录制的代码安全存档于: {output_script_path}")
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")


def run_action_plan_only_mode(
    args,
    output_script_path: str,
    resume_context: dict,
) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_PLAN_ONLY)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    _emit_run_started(reporter, args, output_script_path, MODE_PLAN_ONLY)
    _apply_resume_summary(reporter, resume_context)

    try:
        action_data = _build_inline_action_data(args)
        plan = {
            "current_state_summary": f"即时动作 [{action_data['name']}] 预览",
            "planned_steps": [action_data["name"]],
            "suggested_assertion": "",
            "risks": [],
        }
        action_summary = _build_action_summary(args, action_data)
        reporter.update_control_summary(
            control_kind="action",
            control_label=action_summary["action_name"],
            source_ref="inline://action",
            action=action_summary["action"],
            locator_type=action_summary["locator_type"],
            locator_value=action_summary["locator_value"],
            extra_value=action_summary["extra_value"],
        )
        reporter.emit_event(
            "action_loaded",
            action_name=action_summary["action_name"],
            action=action_summary["action"],
            locator_type=action_summary["locator_type"],
            locator_value=action_summary["locator_value"],
        )
        reporter.emit_event(
            "plan_generated",
            current_state_summary=plan["current_state_summary"],
            planned_steps=plan["planned_steps"],
            suggested_assertion="",
            risks=[],
        )
        reporter.update_summary(plan_preview=plan, action_summary=action_summary)

        log.info(f"🧭 [Action] 即时动作名称: {action_summary['action_name']}")
        log.info(f"🧭 [Action] 预览步骤: {action_summary['action_name']}")

        final_status = "success"
        exit_code = 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("action_plan_failed", error=str(e))
        log.error(f"❌ [Action] 计划生成失败: {e}")
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=1 if final_status == "success" else 0,
            last_error=final_error,
        )
    return exit_code


def run_action_dry_run_mode(
    args,
    output_script_path: str,
    resume_context: dict,
) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_DRY_RUN)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    adapter = None
    preview_steps = []
    _emit_run_started(reporter, args, output_script_path, MODE_DRY_RUN)
    _apply_resume_summary(reporter, resume_context)

    try:
        action_data = _build_inline_action_data(args)
        action_summary = _build_action_summary(args, action_data)
        reporter.update_control_summary(
            control_kind="action",
            control_label=action_summary["action_name"],
            source_ref="inline://action",
            action=action_summary["action"],
            locator_type=action_summary["locator_type"],
            locator_value=action_summary["locator_value"],
            extra_value=action_summary["extra_value"],
        )
        reporter.emit_event(
            "action_loaded",
            action_name=action_summary["action_name"],
            action=action_summary["action"],
            locator_type=action_summary["locator_type"],
            locator_value=action_summary["locator_value"],
        )

        adapter = _connect_adapter(args, reporter)
        resolution = _preview_action_resolution(
            adapter.driver, args.platform, action_data
        )
        resolution_hint = _build_resolution_hint(args, action_data, resolution)
        preview = {
            "step": 1,
            "name": action_data["name"],
            "action": action_data["action"],
            "locator_type": action_data["locator_type"],
            "locator_value": action_data["locator_value"],
            "extra_value": action_data["extra_value"],
            "resolvable": resolution.get("resolvable", False),
            "resolution_error": resolution.get("resolution_error", ""),
            "resolution_hint": resolution_hint,
        }
        preview_steps.append(preview)
        reporter.emit_event("action_step_preview", **preview)

        reporter.update_summary(
            action_summary=_build_action_summary(
                args,
                action_data,
                resolvable=preview["resolvable"],
                resolution_error=preview["resolution_error"],
                resolution_hint=preview["resolution_hint"],
            ),
            dry_run_preview={
                "workflow": False,
                "step_count": 1,
                "unresolved_steps": 0 if preview["resolvable"] else 1,
                "preview_steps": preview_steps,
            },
        )
        reporter.update_control_summary(
            resolvable=preview["resolvable"],
            resolution_error=preview["resolution_error"],
            resolution_hint=preview["resolution_hint"],
        )

        if preview["resolvable"]:
            final_status = "success"
            exit_code = 0
        else:
            final_error = "即时动作无法解析"
            exit_code = 1
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("action_dry_run_failed", error=str(e))
        log.error(f"❌ [Action] 模拟执行失败: {e}")
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=len(preview_steps),
            last_error=final_error,
        )
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")
    return exit_code


def run_action_default_mode(
    args,
    output_script_path: str,
    resume_context: dict,
) -> int:
    adapter = None
    reporter = _build_reporter(args, output_script_path, MODE_RUN)
    exit_code = 1
    final_status = "failed"
    final_error = ""
    steps_executed = 0
    _emit_run_started(reporter, args, output_script_path, MODE_RUN)
    _apply_resume_summary(reporter, resume_context)

    try:
        action_data = _build_inline_action_data(args)
        action_summary = _build_action_summary(args, action_data, executed_steps=0)
        reporter.update_control_summary(
            control_kind="action",
            control_label=action_summary["action_name"],
            source_ref="inline://action",
            action=action_summary["action"],
            locator_type=action_summary["locator_type"],
            locator_value=action_summary["locator_value"],
            extra_value=action_summary["extra_value"],
        )
        reporter.emit_event(
            "action_loaded",
            action_name=action_summary["action_name"],
            action=action_summary["action"],
            locator_type=action_summary["locator_type"],
            locator_value=action_summary["locator_value"],
        )

        try:
            adapter = _connect_adapter(args, reporter)
            device = adapter.driver
        except Exception as e:
            final_error = str(e)
            reporter.emit_event("startup_failed", platform=args.platform, error=str(e))
            log.error(f"❌ [Error]{args.platform} 连接失败: {e}")
            return 1

        _ensure_history_manager()
        _ensure_executor_runtime()
        history_manager = StepHistoryManager(initial_content=get_initial_header())
        save_to_disk(output_script_path, get_initial_header())
        executor = UIExecutor(device, platform=args.platform)

        reporter.emit_event(
            "step_started",
            step=1,
            source="action",
            step_name=action_data["name"],
        )
        result = executor.execute_and_record(action_data)
        if not result.get("success"):
            final_error = f"即时动作执行失败: {action_data['name']}"
            reporter.emit_event(
                "action_executed",
                step=1,
                success=False,
                action_description=action_data["name"],
            )
            log.error(f"❌ [Action] 执行失败: {action_data['name']}")
            return 1

        history_manager.add_step(result["code_lines"], result["action_description"])
        save_to_disk(output_script_path, history_manager.get_current_file_content())
        reporter.emit_event(
            "action_executed",
            step=1,
            success=True,
            action_description=result["action_description"],
        )
        steps_executed = 1
        reporter.update_summary(
            action_summary=_build_action_summary(
                args, action_data, executed_steps=steps_executed
            )
        )
        reporter.update_control_summary(executed_steps=steps_executed)
        final_status = "success"
        exit_code = 0
        return 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("action_run_failed", error=str(e))
        log.error(f"❌ [Action] 执行失败: {e}")
        return 1
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=final_error,
        )
        log.info(f"🏁 任务结束，当前已录制的代码安全存档于: {output_script_path}")
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")


def run_default_mode(
    args,
    output_script_path: str,
    context_content: str,
    resume_context: dict,
) -> int:
    adapter = None
    reporter = _build_reporter(args, output_script_path, MODE_RUN)
    exit_code = 1
    final_status = "failed"
    final_error = ""
    steps_executed = 0
    _emit_run_started(reporter, args, output_script_path, MODE_RUN)
    _apply_resume_summary(reporter, resume_context)

    try:
        try:
            adapter = _connect_adapter(args, reporter)
            device = adapter.driver
        except Exception as e:
            final_error = str(e)
            reporter.emit_event("startup_failed", platform=args.platform, error=str(e))
            log.error(f"❌ [Error]{args.platform} 连接失败: {e}")
            return 1

        _ensure_history_manager()
        _ensure_executor_runtime()
        history_manager = StepHistoryManager(initial_content=get_initial_header())
        save_to_disk(output_script_path, get_initial_header())

        _ensure_runtime_classes()
        brain = AutonomousBrain()
        executor = UIExecutor(device, platform=args.platform)

        step_count = 0
        last_error = ""
        consecutive_failures = 0
        last_ui_json = ""

        while step_count < args.max_steps:
            step_count += 1
            steps_executed = step_count
            log.info(f"\n--- 🔄 第 {step_count} 轮探索 ---")
            reporter.emit_event("step_started", step=step_count)

            ui_json, screenshot_base64 = _capture_ui_state(
                args, adapter, reporter, step_count
            )
            current_history = history_manager.get_history()

            if last_ui_json == ui_json and step_count > 1 and not last_error:
                last_error = "【系统环境警告】: 上一步动作已被物理执行，但页面 UI 没有任何改变！可能原因：1.输入项不合法导致按钮无效 2.需要先勾选协议 3.遇到了不可见弹窗。请切勿重复执行相同的动作，请更换策略！"
                log.warning("⚠️ 检测到 UI 僵死(操作无响应)，已向大模型注入防重复警告。")

            last_ui_json = ui_json

            decision_data = brain.get_next_autonomous_action(
                goal=args.goal,
                context=context_content,
                ui_json=ui_json,
                history=current_history,
                platform=args.platform,
                last_error=last_error,
                screenshot_base64=screenshot_base64,
            )

            status = decision_data.get("status")
            action_data = decision_data.get("result", {})
            last_error = ""
            reporter.emit_event(
                "decision_received",
                step=step_count,
                status=status,
                action=action_data.get("action", ""),
                locator_type=action_data.get("locator_type", ""),
                locator_value=action_data.get("locator_value", ""),
            )

            if status == "success":
                if action_data and action_data.get("action"):
                    log.info(
                        "🔍 检测到伴随 success 状态的最终动作/断言，正在执行固化..."
                    )
                    result = executor.execute_and_record(action_data)
                    if result.get("success"):
                        history_manager.add_step(
                            result["code_lines"], result["action_description"]
                        )
                        save_to_disk(
                            output_script_path,
                            history_manager.get_current_file_content(),
                        )
                        log.info(f"✅ 最终动作执行成功: {result['action_description']}")
                        reporter.emit_event(
                            "action_executed",
                            step=step_count,
                            success=True,
                            action_description=result["action_description"],
                        )
                    else:
                        final_error = "最终动作/断言执行失败，任务验证未通过"
                        reporter.emit_event(
                            "action_executed",
                            step=step_count,
                            success=False,
                            action_description="final_action_failed",
                        )
                        log.error("❌ 最终动作/断言执行失败，任务验证未通过！")
                        return 1

                final_status = "success"
                exit_code = 0
                log.info("🎉 [Agent 结论]: 核心目标与断言已全部达成！")
                return 0

            if status == "failed":
                final_error = "任务无法继续，AI 主动判断为失败"
                log.warning("⚠️ [Agent 结论]: 任务无法继续，AI 主动判断为失败。")
                return 1

            if status == "running":
                if not action_data:
                    last_error = "模型返回了 running 状态，但没有提供具体的 action。请提供明确的动作。"
                    consecutive_failures += 1
                    reporter.emit_event(
                        "action_executed",
                        step=step_count,
                        success=False,
                        action_description="missing_action",
                    )
                else:
                    result = executor.execute_and_record(action_data)
                    if result.get("success"):
                        consecutive_failures = 0
                        history_manager.add_step(
                            result["code_lines"], result["action_description"]
                        )
                        save_to_disk(
                            output_script_path,
                            history_manager.get_current_file_content(),
                        )
                        log.info(f"✅ 动作执行成功: {result['action_description']}")
                        reporter.emit_event(
                            "action_executed",
                            step=step_count,
                            success=True,
                            action_description=result["action_description"],
                        )
                    else:
                        consecutive_failures += 1
                        action_repr = f"{action_data.get('action')} - {action_data.get('locator_type')}={action_data.get('locator_value')}"
                        last_error = f"尝试执行动作 [{action_repr}] 失败！未在当前页面找到该元素，或元素不可操作。"
                        reporter.emit_event(
                            "action_executed",
                            step=step_count,
                            success=False,
                            action_description=action_repr,
                        )
                        log.warning(
                            f"⚠️ 执行受挫，准备让大模型进行第 {consecutive_failures} 次自愈尝试..."
                        )

                if consecutive_failures >= args.max_retries:
                    final_error = f"连续重试 {args.max_retries} 次均失败，触发熔断机制"
                    log.error(
                        f"❌ 连续重试 {args.max_retries} 次均失败，触发熔断机制！"
                    )
                    return 1
                continue

            final_error = f"未知的状态字: {status}"
            log.error(f"❌ 未知的状态字: {status}")
            return 1

        final_error = f"探索超过最大步数限制 ({args.max_steps}步)，可能是逻辑死循环"
        log.warning(
            f"⚠️ 探索超过最大步数限制 ({args.max_steps}步)，可能是逻辑死循环，强制终止。"
        )
        return 1

    except KeyboardInterrupt:
        final_error = "收到外部强杀信号 (KeyboardInterrupt)"
        reporter.emit_event("interrupted", reason="KeyboardInterrupt")
        log.warning("\n⚠️ 收到外部强杀信号 (KeyboardInterrupt)！正在安全中止...")
        return 1

    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=final_error,
        )
        log.info(f"🏁 任务结束，当前已录制的代码安全存档于: {output_script_path}")
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        validate_cli_args(args)
    except ValueError as e:
        log.error(f"❌ [CLI] 参数校验失败: {e}")
        sys.exit(2)

    if args.tool_stdin:
        sys.exit(run_tool_stdin_mode(args))

    if args.mcp_server:
        sys.exit(run_mcp_server_mode(args))

    if args.tool_request:
        sys.exit(run_tool_request_mode(args))

    if args.capabilities:
        sys.exit(run_capabilities_mode(args))

    execution_mode = resolve_execution_mode(
        doctor=args.doctor,
        plan_only=args.plan_only,
        dry_run=args.dry_run,
    )
    output_script_path = _resolve_output_script_path(args)

    log.info("=" * 60)
    log.info("🚀 启动 ScreenForge UI 测试引擎")
    target_label = (
        args.goal
        or getattr(args, "action_name", "")
        or getattr(args, "action", "")
        or args.workflow
        or "doctor / no-goal mode"
    )
    log.info(f"🎯 核心目标: {target_label}")
    log.info(f"🛡️ 熔断配置: 单步最多连续重试 {args.max_retries} 次")
    log.info(
        f"📱 目标平台: {args.platform} | 👁️ 视觉辅助: {'开启' if args.vision else '关闭'}"
    )
    log.info(f"🧭 运行模式: {execution_mode}")
    log.info(f"📁 目标文件: {output_script_path}")
    log.info("=" * 60)

    try:
        context_content, resume_context = _load_context_content(args)
    except RunContextLoadError as e:
        log.error(f"❌ [CLI] 恢复上下文失败: {e}")
        sys.exit(2)

    if execution_mode != MODE_DOCTOR and not config.validate_config():
        log.error("❌ [Config] 配置校验失败，请检查上述错误信息")
        sys.exit(1)

    sys.exit(
        _dispatch_execution(
            args,
            execution_mode,
            output_script_path,
            context_content,
            resume_context,
        )
    )


if __name__ == "__main__":
    main()
