import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import config.config as config
from common.logs import log


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _resolve_project_root() -> Path:
    return Path(getattr(config, "BASE_DIR", Path.cwd())).resolve()


def _build_resume_commands(run_id: str, platform: str) -> Dict[str, str]:
    if not str(run_id).strip() or not str(platform).strip():
        return {}

    return {
        "plan_only": f"./.venv/bin/python agent_cli.py --resume-run-id {run_id} --platform {platform} --plan-only",
        "dry_run": f"./.venv/bin/python agent_cli.py --resume-run-id {run_id} --platform {platform} --dry-run",
        "run": f"./.venv/bin/python agent_cli.py --resume-run-id {run_id} --platform {platform}",
        "doctor": f"./.venv/bin/python agent_cli.py --doctor --platform {platform}",
    }


def _build_pytest_asset(
    output_script_path: str,
    run_id: str = "",
    platform: str = "",
    manifest_path: str = "",
) -> Dict[str, Any]:
    raw_path = Path(str(output_script_path))
    project_root = _resolve_project_root()
    resolved_path = raw_path if raw_path.is_absolute() else (project_root / raw_path).resolve()

    try:
        pytest_target = str(resolved_path.relative_to(project_root))
    except ValueError:
        pytest_target = str(resolved_path if raw_path.is_absolute() else raw_path)

    exists = resolved_path.exists()
    return {
        "script_path": str(output_script_path),
        "pytest_target": pytest_target,
        "pytest_command": f"./.venv/bin/python -m pytest {pytest_target}",
        "manifest_path": str(manifest_path),
        "exists": exists,
        "replay_ready": exists,
        "resume_commands": _build_resume_commands(run_id, platform),
    }


def _build_failure_analysis(
    run_id: str,
    platform: str,
    execution_mode: str,
    status: str,
    exit_code: int,
    steps_executed: int,
    last_error: str,
    pytest_asset: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if status == "success" and exit_code == 0 and not str(last_error).strip():
        return None

    error_text = str(last_error or "").strip()
    lowered_error = error_text.lower()
    category = "execution_failure"
    stage = "execution"
    summary = "执行链路失败，需要结合上下文继续排查"
    recovery_hint = "建议先基于最近一次运行做 dry-run 复核，再决定是否直接重试。"
    recommended_mode = "dry_run"
    retryable = True

    if any(token in lowered_error for token in ("operation not permitted", "permission denied", " eperm")) or "当前运行环境限制了" in error_text:
        category = "environment_restricted"
        stage = "preflight"
        summary = "当前运行环境限制了本地设备或浏览器连接"
        recovery_hint = "建议先在宿主终端执行 doctor 或 dry-run，确认不是沙箱权限导致的假阴性。"
        recommended_mode = "doctor"
        retryable = False
    elif any(token in error_text for token in ("未找到", "不可操作", "未出现")):
        category = "locator_resolution"
        stage = "execution"
        summary = "当前页面未成功定位到目标元素，或元素状态不可操作"
        recovery_hint = "建议先做 dry-run 复核定位策略，再基于恢复上下文继续重试。"
        recommended_mode = "dry_run"
    elif any(token in error_text for token in ("连续重试", "熔断", "最大步数", "死循环")):
        category = "stagnation"
        stage = "planning" if execution_mode in {"plan_only", "dry_run"} else "execution"
        summary = "执行过程触发了重试上限或步数上限"
        recovery_hint = "建议先做计划预演，再缩小目标范围或补充业务上下文。"
        recommended_mode = "plan_only"
    elif any(token in error_text for token in ("未配置", "配置校验失败")) or any(
        token in lowered_error for token in ("api_key", "base_url", "config")
    ):
        category = "configuration"
        stage = "preflight"
        summary = "运行前置配置不完整或不合法"
        recovery_hint = "建议先执行 doctor 修复配置，再重新运行。"
        recommended_mode = "doctor"
        retryable = False
    elif steps_executed == 0:
        stage = "startup"

    resume_commands = pytest_asset.get("resume_commands", {}) or _build_resume_commands(
        run_id, platform
    )
    suggested_commands = []
    if recommended_mode == "doctor":
        suggested_commands.append(
            resume_commands.get(
                "doctor",
                f"./.venv/bin/python agent_cli.py --doctor --platform {platform}",
            )
        )
    elif recommended_mode == "plan_only":
        suggested_commands.append(
            resume_commands.get(
                "plan_only",
                f"./.venv/bin/python agent_cli.py --resume-run-id {run_id} --platform {platform} --plan-only",
            )
        )
    else:
        suggested_commands.append(
            resume_commands.get(
                "dry_run",
                f"./.venv/bin/python agent_cli.py --resume-run-id {run_id} --platform {platform} --dry-run",
            )
        )

    if pytest_asset.get("replay_ready") and retryable:
        suggested_commands.append(pytest_asset["pytest_command"])

    recommended_command = suggested_commands[0] if suggested_commands else ""

    return {
        "category": category,
        "stage": stage,
        "summary": summary,
        "recovery_hint": recovery_hint,
        "retryable": retryable,
        "recommended_mode": recommended_mode,
        "recommended_command": recommended_command,
        "execution_mode": execution_mode,
        "steps_executed": steps_executed,
        "last_error": error_text,
        "suggested_commands": suggested_commands,
    }


def _build_pytest_replay_manifest(
    summary: Dict[str, Any],
    pytest_asset: Dict[str, Any],
    failure_analysis: Optional[Dict[str, Any]],
    summary_path: Path,
    artifacts_path: Path,
) -> Dict[str, Any]:
    return {
        "run_id": summary.get("run_id", ""),
        "generated_at": summary.get("finished_at", "") or _now_iso(),
        "platform": summary.get("platform", ""),
        "env": summary.get("env", ""),
        "execution_mode": summary.get("execution_mode", ""),
        "status": summary.get("status", ""),
        "exit_code": summary.get("exit_code"),
        "control_summary": summary.get("control_summary", {}) or {},
        "output_script_path": summary.get("output_script_path", ""),
        "summary_path": str(summary_path),
        "artifacts_path": str(artifacts_path),
        "failure_analysis": failure_analysis,
        "pytest_asset": pytest_asset,
        "resume_commands": pytest_asset.get("resume_commands", {}) or {},
    }


class RunReporter:
    def __init__(
        self,
        goal: str,
        platform: str,
        env_name: str,
        output_script_path: str,
        json_output: bool = False,
        vision_enabled: bool = False,
        max_steps: int = 0,
        base_dir: Optional[str] = None,
        execution_mode: str = "run",
        resume_from_run_id: str = "",
        control_kind: str = "goal",
        control_label: str = "",
        control_source_ref: str = "",
    ):
        self.run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        self._json_output = json_output
        self._base_dir = Path(base_dir or config.RUN_REPORT_BASE_DIR) / self.run_id
        self._screenshots_dir = self._base_dir / "screenshots"
        self._steps_file = self._base_dir / "steps.jsonl"
        self._summary_file = self._base_dir / "summary.json"
        self._artifacts_file = self._base_dir / "artifacts.json"
        self._pytest_manifest_file = self._base_dir / "pytest_replay.json"
        self._finished = False
        self._output_script_path = str(output_script_path)

        self._base_dir.mkdir(parents=True, exist_ok=True)
        pytest_asset = _build_pytest_asset(
            output_script_path,
            run_id=self.run_id,
            platform=platform,
            manifest_path=str(self._pytest_manifest_file),
        )

        self._artifacts: Dict[str, Any] = {
            "generated_script": {
                "path": str(output_script_path),
                "pytest_target": pytest_asset["pytest_target"],
                "pytest_command": pytest_asset["pytest_command"],
                "manifest_path": pytest_asset["manifest_path"],
                "exists": pytest_asset["exists"],
                "replay_ready": pytest_asset["replay_ready"],
            },
            "pytest_manifest": {
                "path": str(self._pytest_manifest_file),
                "exists": False,
            },
            "steps_file": {"path": str(self._steps_file)},
            "summary_file": {"path": str(self._summary_file)},
            "screenshots": [],
            "videos": [],
        }
        self._summary: Dict[str, Any] = {
            "run_id": self.run_id,
            "goal": goal,
            "platform": platform,
            "env": env_name,
            "execution_mode": execution_mode,
            "resume_from_run_id": resume_from_run_id,
            "resume_context_available": bool(resume_from_run_id),
            "plan_preview": None,
            "dry_run_preview": None,
            "doctor_summary": None,
            "failure_analysis": None,
            "pytest_asset": pytest_asset,
            "control_summary": {
                "control_kind": control_kind,
                "control_label": control_label or goal,
                "source_ref": control_source_ref,
                "execution_mode": execution_mode,
            },
            "vision_enabled": vision_enabled,
            "max_steps": max_steps,
            "output_script_path": str(output_script_path),
            "status": "running",
            "exit_code": None,
            "steps_executed": 0,
            "last_error": "",
            "started_at": _now_iso(),
            "finished_at": None,
            "artifacts_path": str(self._artifacts_file),
        }
        self._write_json(self._artifacts_file, self._artifacts)
        self._write_json(self._summary_file, self._summary)

    def update_summary(self, **fields: Any) -> None:
        self._summary.update(fields)
        self._write_json(self._summary_file, self._summary)

    def update_control_summary(self, **fields: Any) -> None:
        control_summary = self._summary.setdefault("control_summary", {})
        control_summary.update(fields)
        self._write_json(self._summary_file, self._summary)

    @property
    def run_dir(self) -> Path:
        return self._base_dir

    def emit_event(self, event: str, **payload: Any) -> None:
        record = {
            "timestamp": _now_iso(),
            "run_id": self.run_id,
            "event": event,
            **payload,
        }
        try:
            with self._steps_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if self._json_output:
                print(json.dumps(record, ensure_ascii=False), file=sys.stdout, flush=True)
        except Exception as e:
            log.warning(f"⚠️ [Warning] 写入运行事件失败: {e}")

    def save_screenshot(
        self, img_bytes: bytes, step_index: int, name: Optional[str] = None
    ) -> str:
        if not img_bytes:
            return ""

        self._screenshots_dir.mkdir(parents=True, exist_ok=True)
        file_name = name or f"step_{step_index:03d}.png"
        screenshot_path = self._screenshots_dir / file_name
        try:
            screenshot_path.write_bytes(img_bytes)
            artifact = {
                "path": str(screenshot_path),
                "step": step_index,
                "name": file_name,
            }
            self._artifacts["screenshots"].append(artifact)
            self._write_json(self._artifacts_file, self._artifacts)
            self.emit_event(
                "artifact_saved",
                artifact_type="screenshot",
                step=step_index,
                path=str(screenshot_path),
            )
            return str(screenshot_path)
        except Exception as e:
            log.warning(f"⚠️ [Warning] 保存运行截图失败: {e}")
            return ""

    def finalize(
        self,
        status: str,
        exit_code: int,
        steps_executed: int,
        last_error: str = "",
    ) -> None:
        if self._finished:
            return

        pytest_asset = _build_pytest_asset(
            self._output_script_path,
            run_id=self.run_id,
            platform=self._summary.get("platform", ""),
            manifest_path=str(self._pytest_manifest_file),
        )
        self._summary["pytest_asset"] = pytest_asset
        self._artifacts["generated_script"].update(
            {
                "pytest_target": pytest_asset["pytest_target"],
                "pytest_command": pytest_asset["pytest_command"],
                "manifest_path": pytest_asset["manifest_path"],
                "exists": pytest_asset["exists"],
                "replay_ready": pytest_asset["replay_ready"],
            }
        )
        failure_analysis = _build_failure_analysis(
            run_id=self.run_id,
            platform=self._summary.get("platform", ""),
            execution_mode=self._summary.get("execution_mode", "run"),
            status=status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=last_error,
            pytest_asset=pytest_asset,
        )
        self._summary["failure_analysis"] = failure_analysis
        self._summary.update(
            {
                "status": status,
                "exit_code": exit_code,
                "steps_executed": steps_executed,
                "last_error": last_error,
                "finished_at": _now_iso(),
            }
        )
        replay_manifest = _build_pytest_replay_manifest(
            summary=self._summary,
            pytest_asset=pytest_asset,
            failure_analysis=failure_analysis,
            summary_path=self._summary_file,
            artifacts_path=self._artifacts_file,
        )
        self._artifacts["pytest_manifest"]["exists"] = True
        self._write_json(self._summary_file, self._summary)
        self._write_json(self._artifacts_file, self._artifacts)
        self._write_json(self._pytest_manifest_file, replay_manifest)
        self.emit_event(
            "run_finished",
            status=status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=last_error,
        )
        self._finished = True

    @staticmethod
    def _write_json(file_path: Path, data: Dict[str, Any]) -> None:
        tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_path.replace(file_path)
