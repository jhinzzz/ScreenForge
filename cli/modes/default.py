"""Default autonomous brain loop mode."""

import cli.shared as _shared
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
    _ensure_runtime_classes,
    get_initial_header,
    log,
    save_to_disk,
)
from common.runtime_modes import MODE_RUN


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
        history_manager = _shared.StepHistoryManager(initial_content=get_initial_header())
        save_to_disk(output_script_path, get_initial_header())

        _ensure_runtime_classes()
        brain = _shared.AutonomousBrain()
        executor = _shared.UIExecutor(device, platform=args.platform)

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
                log.warning("[E020] UI stagnation detected: action executed but page did not change. Possible causes: invalid input, unchecked checkbox, or invisible overlay.")

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
                        log.info(f"Action succeeded: {result['action_description']}")
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
                            f"[E021] Step failed (attempt {consecutive_failures}/{args.max_retries}). Self-heal engine will retry with adjusted strategy."
                        )

                if consecutive_failures >= args.max_retries:
                    action_repr = f"{action_data.get('action')} - {action_data.get('locator_type')}={action_data.get('locator_value')}"
                    final_error = f"Circuit breaker triggered after {args.max_retries} consecutive failures on: {action_repr}"
                    log.error(
                        f"[E022] Circuit breaker triggered: {args.max_retries} consecutive failures on [{action_repr}]. "
                        f"Last error: element not found or not interactable. "
                        f"Fix: run 'screenforge --action click --platform {args.platform} --dry-run ...' to inspect current page state, "
                        f"or adjust your workflow/locator strategy."
                    )
                    return 1
                continue

            final_error = f"Unknown decision status: {status}"
            log.error(f"[E023] Unknown decision status '{status}' returned by AI brain. This is likely a model parsing issue. Fix: check MODEL_NAME supports structured JSON output")
            return 1

        final_error = f"Max step limit reached ({args.max_steps} steps)"
        log.warning(
            f"[E024] Exploration exceeded max step limit ({args.max_steps}). Possible infinite loop. Fix: increase --max_steps or refine your --goal to be more specific."
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
