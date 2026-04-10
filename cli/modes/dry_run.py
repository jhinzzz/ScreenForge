"""Dry-run execution modes."""

from common.runtime_modes import MODE_DRY_RUN

from cli.reporter import (
    _apply_resume_summary,
    _build_action_summary,
    _build_inline_action_data,
    _build_reporter,
    _emit_run_started,
)
from cli.shared import (
    AutonomousBrain,
    _capture_ui_state,
    _connect_adapter,
    _ensure_executor_runtime,
    _ensure_runtime_classes,
    get_actual_element,
    log,
)


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
