import json
from pathlib import Path
from typing import Any, Dict, List


class RunContextLoadError(Exception):
    pass


def _read_summary(summary_file: Path) -> Dict[str, object]:
    if not summary_file.exists():
        raise RunContextLoadError(f"未找到可恢复的运行记录: {summary_file.parent}")
    return json.loads(summary_file.read_text(encoding="utf-8"))


def _read_optional_json(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def _read_steps(steps_file: Path) -> List[Dict[str, object]]:
    if not steps_file.exists():
        return []

    records: List[Dict[str, object]] = []
    with steps_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _build_recommended_next_step(
    failure_analysis: Dict[str, Any] | None,
    resume_commands: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    failure_analysis = failure_analysis or {}
    if not failure_analysis:
        return None

    resume_commands = resume_commands or {}
    recommended_mode = str(failure_analysis.get("recommended_mode", "")).strip()
    if not recommended_mode:
        category = str(failure_analysis.get("category", "")).strip()
        if category in {"configuration", "environment_restricted"}:
            recommended_mode = "doctor"
        elif category == "stagnation":
            recommended_mode = "plan_only"
        else:
            recommended_mode = "dry_run"
    recommended_command = str(failure_analysis.get("recommended_command", "")).strip()
    if not recommended_command and recommended_mode:
        recommended_command = str(resume_commands.get(recommended_mode, "")).strip()

    return {
        "category": failure_analysis.get("category", ""),
        "stage": failure_analysis.get("stage", ""),
        "summary": failure_analysis.get("summary", ""),
        "retryable": failure_analysis.get("retryable"),
        "recommended_mode": recommended_mode,
        "recommended_command": recommended_command,
        "recovery_hint": failure_analysis.get("recovery_hint", ""),
    }


def load_run_context(run_dir: Path) -> Dict[str, object]:
    run_dir = Path(run_dir)
    try:
        summary = _read_summary(run_dir / "summary.json")
        steps = _read_steps(run_dir / "steps.jsonl")
    except RunContextLoadError:
        raise
    except Exception as exc:
        raise RunContextLoadError(f"读取运行记录失败: {run_dir}") from exc

    successful_actions = [
        item.get("action_description", "")
        for item in steps
        if item.get("event") == "action_executed"
        and item.get("success") is True
        and item.get("action_description")
    ]

    latest_screenshot_path = ""
    for item in steps:
        if item.get("event") == "artifact_saved" and item.get("artifact_type") == "screenshot":
            latest_screenshot_path = item.get("path", "") or latest_screenshot_path

    return {
        "run_id": summary.get("run_id", ""),
        "goal": summary.get("goal", ""),
        "platform": summary.get("platform", ""),
        "env": summary.get("env", ""),
        "status": summary.get("status", ""),
        "last_error": summary.get("last_error", ""),
        "failure_analysis": summary.get("failure_analysis", {}) or {},
        "pytest_asset": summary.get("pytest_asset", {}) or {},
        "control_summary": summary.get("control_summary", {}) or {},
        "successful_actions": successful_actions,
        "latest_screenshot_path": latest_screenshot_path,
    }


def load_run_bundle(run_dir: Path) -> Dict[str, object]:
    run_dir = Path(run_dir)
    summary_file = run_dir / "summary.json"
    artifacts_file = run_dir / "artifacts.json"
    pytest_replay_file = run_dir / "pytest_replay.json"

    summary = _read_summary(summary_file)
    artifacts = _read_optional_json(artifacts_file)
    pytest_replay = _read_optional_json(pytest_replay_file)
    resume_context = load_run_context(run_dir)

    pytest_asset = summary.get("pytest_asset", {}) or {}
    failure_analysis = summary.get("failure_analysis", None)
    resume_commands = {
        **(pytest_asset.get("resume_commands", {}) or {}),
        **(pytest_replay.get("resume_commands", {}) or {}),
    }
    run_assets = {
        "summary_path": str(summary_file),
        "artifacts_path": str(artifacts_file) if artifacts_file.exists() else "",
        "pytest_replay_path": str(pytest_replay_file)
        if pytest_replay_file.exists()
        else str(pytest_asset.get("manifest_path", "") or ""),
        "failure_analysis": failure_analysis,
        "pytest_asset": pytest_asset,
        "resume_commands": resume_commands,
        "recommended_next_step": _build_recommended_next_step(
            failure_analysis,
            resume_commands,
        ),
    }

    return {
        "run_id": summary.get("run_id", ""),
        "run_dir": str(run_dir),
        "summary": summary,
        "artifacts": artifacts,
        "pytest_replay": pytest_replay,
        "resume_context": resume_context,
        "run_assets": run_assets,
    }
