"""Plan-only execution modes."""

from common.runtime_modes import MODE_PLAN_ONLY

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
    _ensure_runtime_classes,
    log,
)


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
