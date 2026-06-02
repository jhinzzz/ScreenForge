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


def _run_session_end(args) -> int:
    from cli.session import delete_session, load_session, stop_session_recording

    session_id = args.session_end
    session = load_session(session_id)
    if not session:
        log.error(f"❌ Session not found: {session_id}")
        return 1

    output_path = session["output_path"]

    video_path = stop_session_recording(session_id)
    if video_path:
        log.info(f"🎬 [Session] Recording saved: {video_path}")

    delete_session(session_id)
    log.info(f"✅ [Session] Ended session '{session_id}'")
    log.info(f"📄 [Session] Test script: {output_path}")
    log.info(f"📊 [Session] Total steps: {session.get('steps', 0)}")
    return 0


def main():
    from cli.shorthand import preprocess_argv

    processed_argv = preprocess_argv(sys.argv)

    parser = build_parser()
    args = parser.parse_args(processed_argv[1:])

    if getattr(args, "session_end", ""):
        sys.exit(_run_session_end(args))

    if getattr(args, "web_stop", False):
        from common.adapters.web_adapter import stop_persistent_browser

        # Idempotent: stopping a browser, or finding none to stop, both succeed.
        stop_persistent_browser()
        sys.exit(0)

    try:
        validate_cli_args(args)
    except ValueError as e:
        log.error(f"[E010] Invalid CLI arguments: {e}. Fix: run 'screenforge --help' to see valid options")
        sys.exit(2)

    if getattr(args, "init", False):
        from cli.modes.init import run_init_mode

        sys.exit(run_init_mode())

    if getattr(args, "demo", False):
        from cli.modes.demo import run_demo_mode

        sys.exit(run_demo_mode())

    if getattr(args, "playground", False):
        try:
            from playground.app import run_server
        except ImportError:
            log.error("[E013] Playground requires extra dependencies. Fix: pip install screenforge[playground]")
            sys.exit(1)
        cdp_url = "http://127.0.0.1:9333"
        log.info(f"Starting Playground on http://127.0.0.1:{args.playground_port}")
        log.info(f"CDP screencast target: {cdp_url}")
        run_server(port=args.playground_port, cdp_url=cdp_url)
        sys.exit(0)

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

    session_id = getattr(args, "session_id", "")
    shared_adapter_mgr = None
    if session_id and args.action:
        from cli.session import (
            create_session,
            load_session,
            resolve_session_output_path,
            update_session,
        )

        session = load_session(session_id)
        if session:
            output_script_path = session["output_path"]
            shared_adapter_mgr = _SharedAdapterManager()
        else:
            from cli.session import start_session_recording

            output_script_path = resolve_session_output_path(session_id, args.platform)
            session = create_session(session_id, args.platform, output_script_path)
            shared_adapter_mgr = _SharedAdapterManager()
            start_session_recording(session_id, args.platform)
    else:
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

    exit_code = _dispatch_execution(
        args,
        execution_mode,
        output_script_path,
        context_content,
        resume_context,
        shared_adapter_manager=shared_adapter_mgr,
    )

    if session_id and args.action:
        from cli.session import load_session, update_session

        session = load_session(session_id)
        if session and exit_code == 0:
            update_session(session_id, steps=session.get("steps", 0) + 1)

    sys.exit(exit_code)
