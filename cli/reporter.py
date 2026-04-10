"""Reporter helpers, context resolution, and output path management."""

import os
from datetime import datetime
from pathlib import Path

from common.run_resume import RunContextLoadError, load_run_context
from common.runtime_modes import MODE_DOCTOR

from cli.shared import (
    RunReporter,
    _ensure_reporter_class,
    config,
    log,
)


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
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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


def _build_reporter(args, output_script_path: str, execution_mode: str):
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


def _emit_run_started(reporter, args, output_script_path: str, execution_mode: str) -> None:
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


def _apply_resume_summary(reporter, resume_context: dict) -> None:
    reporter.update_summary(
        resume_context_available=bool(resume_context),
    )
    if resume_context:
        reporter.update_control_summary(
            resume_context=resume_context.get("control_summary", {}) or {},
        )
