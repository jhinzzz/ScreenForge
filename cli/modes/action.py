"""Single-action execution mode."""

import json
import os
import sys

import cli.shared as _shared
from cli.reporter import (
    _apply_resume_summary,
    _build_action_summary,
    _build_inline_action_data,
    _build_reporter,
    _emit_run_started,
)
from cli.shared import (
    _capture_ui_state,
    _connect_adapter,
    _ensure_executor_runtime,
    _ensure_history_manager,
    _ensure_ui_compressors,
    _SharedAdapterManager,
    current_url,
    get_initial_header,
    log,
    save_to_disk,
)
from common.failure_diagnosis import diagnose
from common.runtime_modes import MODE_RUN


def build_failure_payload(
    *,
    action_name: str,
    platform: str,
    assertion_failed: bool,
    error_code: str,
    locator_value: str,
    ui_tree: dict,
    current_url: str,
) -> dict:
    """Assemble the --action --json failure payload.

    A failed assertion is a verdict: keep the original bare shape (no diagnosis,
    no page, no retry bait). An engine_error is where the agent needs help, so
    enrich it with the did-you-mean diagnosis, the current ui_tree, and the URL.

    Note: ui_tree, element_count, and current_url are emitted ONLY for
    engine_error — the assertion_failed path returns the bare verdict above.
    """
    payload = {
        "ok": False,
        "action": action_name,
        "platform": platform,
        "result": "assertion_failed" if assertion_failed else "engine_error",
        "assertion_failed": assertion_failed,
        "error": (
            f"Assertion failed: {action_name}"
            if assertion_failed
            else f"Action failed: {action_name}"
        ),
    }
    if assertion_failed:
        return payload

    diag = diagnose(
        error_code=error_code or "E037",
        locator_value=locator_value or "",
        ui_elements=ui_tree.get("ui_elements", []) or [],
    )
    payload.update(diag.to_dict())
    payload["ui_tree"] = ui_tree
    payload["element_count"] = len(ui_tree.get("ui_elements", []) or [])
    payload["current_url"] = current_url
    return payload


def run_action_default_mode(
    args,
    output_script_path: str,
    resume_context: dict,
    shared_adapter_manager: _SharedAdapterManager | None = None,
) -> int:
    adapter = None
    owns_adapter = False
    json_mode = args.json
    reporter = _build_reporter(args, output_script_path, MODE_RUN, json_output=False)
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
            # Name the test after the action so the file is discoverable.
            header = get_initial_header(label=action_data.get("name") or None)
            history_manager = _shared.StepHistoryManager(initial_content=header)
            save_to_disk(output_script_path, header)

        if shared_adapter_manager:
            # Reuse the session's shared executor so a `ref @N` action resolves
            # against the cache a prior inspect_ui populated (same MCP session).
            executor = shared_adapter_manager.get_executor(args.platform, args.env)
        else:
            executor = _shared.UIExecutor(device, platform=args.platform)

        reporter.emit_event(
            "step_started",
            step=1,
            source="action",
            step_name=action_data["name"],
        )
        result = executor.execute_and_record(action_data)
        if not result.get("success"):
            assertion_failed = bool(result.get("assertion_failed"))
            if assertion_failed:
                final_error = f"Assertion failed: {action_data['name']}"
            else:
                final_error = f"Action failed: {action_data['name']}"
            reporter.emit_event(
                "action_executed",
                step=1,
                success=False,
                action_description=action_data["name"],
            )
            log.error(f"❌ [Action] Failed: {action_data['name']}")
            if json_mode:
                # Distinguish a verification verdict (assertion_failed=true: the
                # SUT did not meet the assertion — do NOT retry) from a real
                # engine error. Only engine errors get the did-you-mean
                # diagnosis + current ui_tree (the agent needs the page to
                # recover); a verdict stays a bare result so we never bait a
                # retry on a legitimately-failed assertion.
                # Capture the URL at the moment of failure, BEFORE compress_web_dom
                # traverses the DOM (a mid-redirect click could otherwise settle the
                # navigation and report the post-redirect URL).
                page_url = current_url(adapter, args.platform)
                ui_tree = {}
                if not assertion_failed:
                    _ensure_ui_compressors()
                    try:
                        ui_json, _ = _capture_ui_state(args, adapter, reporter, 1)
                        ui_tree = json.loads(ui_json)
                    except Exception as e:
                        # Degrade (connection lost / non-JSON) but don't hide it:
                        # a silent empty tree yields empty candidates with no signal.
                        log.warning(f"⚠️ [Action] Failed to capture post-failure UI state: {e}")
                        ui_tree = {}
                error_code = result.get("error_code", "") or ""
                if not error_code and not assertion_failed:
                    log.warning("⚠️ [Action] executor returned no error_code; defaulting to E037")
                payload = build_failure_payload(
                    action_name=action_data["name"],
                    platform=args.platform,
                    assertion_failed=assertion_failed,
                    error_code=error_code,
                    locator_value=getattr(args, "locator_value", "") or "",
                    ui_tree=ui_tree,
                    current_url=page_url,
                )
                json.dump(payload, sys.stdout, ensure_ascii=False)
                sys.stdout.write("\n")
                sys.stdout.flush()
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

        if json_mode:
            _ensure_ui_compressors()
            ui_json, _ = _capture_ui_state(args, adapter, reporter, 1)
            try:
                ui_tree = json.loads(ui_json)
            except (json.JSONDecodeError, TypeError):
                ui_tree = {}
            json.dump({
                "ok": True,
                "action": action_data["name"],
                "platform": args.platform,
                "ui_tree": ui_tree,
                "element_count": len(ui_tree.get("ui_elements", [])),
                "output_script": output_script_path,
                "current_url": current_url(adapter, args.platform),
            }, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
            sys.stdout.flush()

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
