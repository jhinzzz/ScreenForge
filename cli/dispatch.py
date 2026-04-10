"""Execution dispatcher and CLI entry point."""

import sys

from common.run_resume import RunContextLoadError
from common.runtime_modes import (
    MODE_DOCTOR,
    MODE_DRY_RUN,
    MODE_PLAN_ONLY,
    resolve_execution_mode,
)

from cli.doctor import run_capabilities_mode, run_doctor_mode
from cli.modes.action import run_action_default_mode
from cli.modes.default import run_default_mode
from cli.modes.dry_run import run_action_dry_run_mode, run_dry_run_mode
from cli.modes.plan import run_action_plan_only_mode, run_plan_only_mode
from cli.modes.workflow import (
    run_workflow_default_mode,
    run_workflow_dry_run_mode,
    run_workflow_plan_only_mode,
)
from cli.parser import build_parser, validate_cli_args
from cli.reporter import _load_context_content, _resolve_output_script_path
from cli.shared import _SharedAdapterManager, config, log
from cli.tool_protocol_handlers import (
    _requires_model_runtime,
    run_mcp_server_mode,
    run_tool_request_mode,
    run_tool_stdin_mode,
)


def _dispatch_execution(
    args,
    execution_mode: str,
    output_script_path: str,
    context_content: str,
    resume_context: dict,
    shared_adapter_manager: _SharedAdapterManager | None = None,
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
            shared_adapter_manager=shared_adapter_manager,
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

    if _requires_model_runtime(args, execution_mode) and not config.validate_config():
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
