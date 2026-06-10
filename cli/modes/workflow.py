"""Workflow execution modes."""

import json
from pathlib import Path

import cli.shared as _shared
from cli.modes.dry_run import _build_resolution_hint, _preview_action_resolution
from cli.playground_sink import build_sink_from_args, maybe_push_step
from cli.reporter import (
    _apply_resume_summary,
    _build_reporter,
    _emit_run_started,
)
from cli.shared import (
    _capture_ui_state,
    _connect_adapter,
    _ensure_executor_runtime,
    _ensure_history_manager,
    _ensure_ui_compressors,
    _ensure_workflow_loader,
    _SharedAdapterManager,
    current_url,
    get_initial_header,
    log,
    save_to_disk,
)
from common.runtime_modes import MODE_DRY_RUN, MODE_PLAN_ONLY, MODE_RUN


def _load_workflow_definition(args):
    _ensure_workflow_loader()
    workflow = _shared.load_workflow_file(args.workflow)
    workflow_var_overrides = _shared.parse_workflow_var_overrides(args.workflow_var)
    workflow = _shared.resolve_workflow_definition(workflow, workflow_var_overrides)

    if workflow.platform and workflow.platform != args.platform:
        raise _shared.WorkflowLoadError(
            f"Workflow platform [{workflow.platform}] conflicts with --platform [{args.platform}]"
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
            "current_state_summary": f"Workflow [{workflow.name or Path(args.workflow).stem}] preview",
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

        log.info(f"🧭 [Workflow] Workflow name: {workflow_summary['workflow_name']}")
        for index, step_name in enumerate(planned_steps, start=1):
            log.info(f"🧭 [Workflow] Step {index}: {step_name}")

        final_status = "success"
        exit_code = 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("workflow_plan_failed", error=str(e))
        log.error(f"❌ [Workflow] Plan generation failed: {e}")
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=0 if final_error else 1,
            last_error=final_error,
        )
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
            final_error = f"{unresolved_steps} workflow step(s) could not be resolved"
            exit_code = 1
        else:
            final_status = "success"
            exit_code = 0
    except Exception as e:
        final_error = str(e)
        reporter.emit_event("workflow_dry_run_failed", error=str(e))
        log.error(f"❌ [Workflow] Dry-run failed: {e}")
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
                log.warning(f"⚠️ [Warning] Cleanup failed: {e}")
    return exit_code


def run_workflow_default_mode(
    args,
    output_script_path: str,
    resume_context: dict,
    shared_adapter_manager: _SharedAdapterManager | None = None,
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
            log.error(f"❌ [Error] {args.platform} connection failed: {e}")
            return 1

        _ensure_history_manager()
        _ensure_executor_runtime()
        header = get_initial_header(label=str(getattr(workflow, "name", "")).strip() or None)
        history_manager = _shared.StepHistoryManager(initial_content=header)
        save_to_disk(output_script_path, header)
        executor = _shared.UIExecutor(device, platform=args.platform)
        # Workflow is one process with many steps (the main use case for live mirror).
        # Build the sink once; join_on_exit=False — the process lives across all steps.
        sink = build_sink_from_args(args, join_on_exit=False)

        executed_steps = 0
        for index, step in enumerate(workflow.steps, start=1):
            if not step.enabled:
                continue

            steps_executed = index
            action_data = _workflow_step_to_action_data(step, index)
            last_action_name = action_data["name"]
            reporter.emit_event(
                "step_started",
                step=index,
                source="workflow",
                step_name=action_data["name"],
            )
            result = executor.execute_and_record(action_data)
            if not result.get("success"):
                final_error = f"Workflow step failed: {action_data['name']}"
                reporter.emit_event(
                    "action_executed",
                    step=index,
                    success=False,
                    action_description=action_data["name"],
                )
                log.error(f"❌ [Workflow] Step failed: {action_data['name']}")
                # ★ MCP parity: stash the FAILING step's observation (single-point
                # failure) with its index/name so the agent knows where the batch
                # stopped. Gated on a manager (MCP/session path) — bare shell pays
                # nothing. NEVER a per-step array (see design doc, decision §).
                if shared_adapter_manager is not None:
                    from cli.modes.action import build_failure_payload
                    assertion_failed = bool(result.get("assertion_failed"))
                    page_url = current_url(adapter, args.platform)
                    fail_ui_tree = {}
                    if not assertion_failed:
                        _ensure_ui_compressors()
                        try:
                            ui_json, _ = _capture_ui_state(args, adapter, reporter, index)
                            fail_ui_tree = json.loads(ui_json)
                        except Exception as e:
                            log.warning(f"⚠️ [Workflow] Failed to capture post-failure UI state: {e}")
                            fail_ui_tree = {}
                    observation = build_failure_payload(
                        action_name=action_data["name"],
                        platform=args.platform,
                        assertion_failed=assertion_failed,
                        error_code=result.get("error_code", "") or "",
                        locator_value=action_data.get("locator_value", "") or "",
                        ui_tree=fail_ui_tree,
                        current_url=page_url,
                    )
                    observation["failed_step_index"] = index
                    observation["failed_step_name"] = action_data["name"]
                    shared_adapter_manager.set_last_observation(observation)
                return 1

            history_manager.add_step(
                result["code_lines"], result["action_description"]
            )
            save_to_disk(output_script_path, history_manager.get_current_file_content())
            # ★ Live-mirror bypass: push this step with its loop counter as step_index.
            maybe_push_step(
                sink,
                args=args,
                reporter=reporter,
                adapter=adapter,
                action_data=action_data,
                result=result,
                step_index=index,
                file_path=output_script_path,  # normalized to abs path inside build_step_event
            )
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
        # ★ MCP parity: stash ONE live observation — the FINAL step's end-state,
        # marked with executed_steps so the agent knows it's the end, not step 1.
        # Gated on a manager; bare shell workflow pays nothing. NEVER per-step.
        if shared_adapter_manager is not None and executed_steps:
            from cli.modes.action import build_success_payload
            _ensure_ui_compressors()
            try:
                ui_json, _ = _capture_ui_state(args, adapter, reporter, steps_executed)
                final_ui_tree = json.loads(ui_json)
            except Exception as e:
                log.warning(f"⚠️ [Workflow] Failed to capture final UI state: {e}")
                final_ui_tree = {}
            observation = build_success_payload(
                action_name=last_action_name,
                platform=args.platform,
                ui_tree=final_ui_tree,
                current_url=current_url(adapter, args.platform),
                output_script=output_script_path,
            )
            observation["executed_steps"] = executed_steps
            shared_adapter_manager.set_last_observation(observation)
        final_status = "success"
        exit_code = 0
        return 0

    except Exception as e:
        final_error = str(e)
        reporter.emit_event("workflow_run_failed", error=str(e))
        log.error(f"❌ [Workflow] Execution failed: {e}")
        return 1

    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=final_error,
        )
        log.info(f"🏁 Done. Generated script saved to: {output_script_path}")
        if adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] Cleanup failed: {e}")
