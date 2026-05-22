"""Single-action execution mode."""

import os

import cli.shared as _shared
from cli.reporter import (
    _apply_resume_summary,
    _build_action_summary,
    _build_inline_action_data,
    _build_reporter,
    _emit_run_started,
)
from cli.shared import (
    _connect_adapter,
    _ensure_executor_runtime,
    _ensure_history_manager,
    _SharedAdapterManager,
    get_initial_header,
    log,
    save_to_disk,
)
from common.runtime_modes import MODE_RUN


def run_action_default_mode(
    args,
    output_script_path: str,
    resume_context: dict,
    shared_adapter_manager: _SharedAdapterManager | None = None,
) -> int:
    adapter = None
    owns_adapter = False
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
            if shared_adapter_manager:
                adapter = shared_adapter_manager.get_or_create(args.platform, args.env)
            else:
                adapter = _connect_adapter(args, reporter)
                owns_adapter = True
            device = adapter.driver
        except Exception as e:
            final_error = str(e)
            reporter.emit_event("startup_failed", platform=args.platform, error=str(e))
            log.error(f"❌ [Error] {args.platform} connection failed: {e}")
            return 1

        _ensure_history_manager()
        _ensure_executor_runtime()

        if os.path.exists(output_script_path):
            with open(output_script_path, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()
            history_manager = _shared.StepHistoryManager(initial_content=existing_lines)
            log.info(f"📎 [System] Append mode: continuing on existing script ({output_script_path})")
        else:
            history_manager = _shared.StepHistoryManager(initial_content=get_initial_header())
            save_to_disk(output_script_path, get_initial_header())

        executor = _shared.UIExecutor(device, platform=args.platform)

        reporter.emit_event(
            "step_started",
            step=1,
            source="action",
            step_name=action_data["name"],
        )
        result = executor.execute_and_record(action_data)
        if not result.get("success"):
            final_error = f"Action failed: {action_data['name']}"
            reporter.emit_event(
                "action_executed",
                step=1,
                success=False,
                action_description=action_data["name"],
            )
            log.error(f"❌ [Action] Failed: {action_data['name']}")
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
        log.error(f"❌ [Action] Failed: {e}")
        return 1
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=final_error,
        )
        log.info(f"🏁 Done. Generated script saved to: {output_script_path}")
        if owns_adapter and adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] Cleanup failed: {e}")
