"""Execution dispatcher and CLI entry point."""

import sys

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
from common.run_resume import RunContextLoadError
from common.runtime_modes import (
    MODE_DOCTOR,
    MODE_DRY_RUN,
    MODE_PLAN_ONLY,
    resolve_execution_mode,
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
    from cli.shorthand import preprocess_argv

    processed_argv = preprocess_argv(sys.argv)

    parser = build_parser()
    args = parser.parse_args(processed_argv[1:])

    try:
        validate_cli_args(args)
    except ValueError as e:
        log.error(f"[E010] Invalid CLI arguments: {e}. Fix: run 'screenforge --help' to see valid options")
        sys.exit(2)

    if getattr(args, "demo", False):
        from cli.modes.demo import run_demo_mode

        sys.exit(run_demo_mode())

    if args.tool_stdin:
        from common.progress import set_tool_mode
        set_tool_mode(True)
        if sys.stdin.isatty():
            import io
            import json as _json
            sys.stdin = io.StringIO(_json.dumps({"operation": "inspect_ui", "platform": args.platform}))
        sys.exit(run_tool_stdin_mode(args))

    if args.mcp_server:
        from common.progress import set_tool_mode
        set_tool_mode(True)
        sys.exit(run_mcp_server_mode(args))

    if args.tool_request:
        from common.progress import set_tool_mode
        set_tool_mode(True)
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
    log.info("Starting ScreenForge UI automation engine")
    target_label = (
        args.goal
        or getattr(args, "action_name", "")
        or getattr(args, "action", "")
        or args.workflow
        or "doctor / no-goal mode"
    )
    log.info(f"Target: {target_label}")
    log.info(f"Circuit breaker: max {args.max_retries} retries per step")
    log.info(
        f"Platform: {args.platform} | Vision: {'on' if args.vision else 'off'}"
    )
    log.info(f"Mode: {execution_mode}")
    log.info(f"Output: {output_script_path}")
    log.info("=" * 60)

    try:
        context_content, resume_context = _load_context_content(args)
    except RunContextLoadError as e:
        log.error(f"[E011] Failed to restore run context: {e}. Fix: check that report/runs/<run_id>/ exists and contains summary.json")
        sys.exit(2)

    if _requires_model_runtime(args, execution_mode) and not config.validate_config():
        log.error("[E012] Configuration validation failed. See errors above for details and fix instructions")
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
