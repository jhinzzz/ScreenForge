"""Tests for common/run_resume.py — run context loading and recovery."""

import json

import pytest

from common.run_resume import (
    RunContextLoadError,
    _build_recommended_next_step,
    load_run_bundle,
    load_run_context,
)


@pytest.fixture
def run_dir(tmp_path):
    """Create a minimal valid run directory."""
    summary = {
        "run_id": "20260101_120000_abc12345",
        "goal": "test login",
        "platform": "web",
        "env": "dev",
        "status": "failed",
        "last_error": "element not found",
        "failure_analysis": {
            "category": "locator_resolution",
            "stage": "execution",
            "summary": "Target element not found",
            "retryable": True,
            "recommended_mode": "dry_run",
            "recommended_command": "screenforge --dry-run",
            "recovery_hint": "Run dry-run to verify locator strategy",
        },
        "pytest_asset": {
            "script_path": "test_cases/web/test_auto.py",
            "pytest_target": "test_cases/web/test_auto.py",
            "pytest_command": "pytest test_cases/web/test_auto.py",
            "resume_commands": {"dry_run": "screenforge --dry-run"},
        },
        "control_summary": {"control_kind": "goal", "execution_mode": "run"},
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    steps = [
        {"event": "action_executed", "success": True, "action_description": "Navigate to login"},
        {"event": "action_executed", "success": True, "action_description": "Click username field"},
        {"event": "action_executed", "success": False, "action_description": "Click submit"},
        {"event": "artifact_saved", "artifact_type": "screenshot", "path": "/tmp/shot.png"},
    ]
    lines = [json.dumps(s) for s in steps]
    (tmp_path / "steps.jsonl").write_text("\n".join(lines), encoding="utf-8")

    return tmp_path


class TestLoadRunContext:
    def test_loads_basic_fields(self, run_dir):
        ctx = load_run_context(run_dir)
        assert ctx["run_id"] == "20260101_120000_abc12345"
        assert ctx["goal"] == "test login"
        assert ctx["platform"] == "web"
        assert ctx["status"] == "failed"

    def test_extracts_successful_actions(self, run_dir):
        ctx = load_run_context(run_dir)
        assert ctx["successful_actions"] == [
            "Navigate to login",
            "Click username field",
        ]

    def test_extracts_latest_screenshot(self, run_dir):
        ctx = load_run_context(run_dir)
        assert ctx["latest_screenshot_path"] == "/tmp/shot.png"

    def test_missing_summary_raises(self, tmp_path):
        with pytest.raises(RunContextLoadError, match="No recoverable run record"):
            load_run_context(tmp_path)

    def test_missing_steps_file_returns_empty_actions(self, tmp_path):
        summary = {"run_id": "x", "goal": "g", "platform": "web", "env": "dev",
                   "status": "success", "last_error": "", "failure_analysis": None,
                   "pytest_asset": None, "control_summary": {}}
        (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        ctx = load_run_context(tmp_path)
        assert ctx["successful_actions"] == []
        assert ctx["latest_screenshot_path"] == ""

    def test_corrupt_summary_raises(self, tmp_path):
        (tmp_path / "summary.json").write_text("not json", encoding="utf-8")
        with pytest.raises(RunContextLoadError, match="Failed to read run record"):
            load_run_context(tmp_path)

    def test_corrupt_steps_raises(self, tmp_path):
        summary = {"run_id": "x", "goal": "g", "platform": "web", "env": "dev",
                   "status": "success", "last_error": "", "failure_analysis": None,
                   "pytest_asset": None, "control_summary": {}}
        (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (tmp_path / "steps.jsonl").write_text('{"event":"ok"}\ninvalid json\n', encoding="utf-8")
        with pytest.raises(RunContextLoadError, match="Failed to read run record"):
            load_run_context(tmp_path)

    def test_latest_screenshot_is_last_one(self, tmp_path):
        summary = {"run_id": "x", "goal": "g", "platform": "web", "env": "dev",
                   "status": "success", "last_error": "", "failure_analysis": None,
                   "pytest_asset": None, "control_summary": {}}
        (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        steps = [
            {"event": "artifact_saved", "artifact_type": "screenshot", "path": "/first.png"},
            {"event": "artifact_saved", "artifact_type": "screenshot", "path": "/second.png"},
        ]
        (tmp_path / "steps.jsonl").write_text(
            "\n".join(json.dumps(s) for s in steps), encoding="utf-8"
        )
        ctx = load_run_context(tmp_path)
        assert ctx["latest_screenshot_path"] == "/second.png"


class TestLoadRunBundle:
    def test_returns_all_sections(self, run_dir):
        bundle = load_run_bundle(run_dir)
        assert "summary" in bundle
        assert "artifacts" in bundle
        assert "resume_context" in bundle
        assert "run_assets" in bundle
        assert bundle["run_id"] == "20260101_120000_abc12345"

    def test_run_assets_has_recommended_next_step(self, run_dir):
        bundle = load_run_bundle(run_dir)
        nxt = bundle["run_assets"]["recommended_next_step"]
        assert nxt is not None
        assert nxt["category"] == "locator_resolution"
        assert nxt["recommended_mode"] == "dry_run"

    def test_missing_artifacts_file_returns_empty(self, run_dir):
        bundle = load_run_bundle(run_dir)
        assert bundle["artifacts"] == {}


class TestBuildRecommendedNextStep:
    def test_returns_none_for_empty_analysis(self):
        assert _build_recommended_next_step(None, None) is None
        assert _build_recommended_next_step({}, {}) is None

    def test_doctor_for_configuration(self):
        analysis = {"category": "configuration", "recommended_mode": "", "recommended_command": ""}
        result = _build_recommended_next_step(analysis, {"doctor": "screenforge --doctor"})
        assert result["recommended_mode"] == "doctor"
        assert result["recommended_command"] == "screenforge --doctor"

    def test_plan_only_for_stagnation(self):
        analysis = {"category": "stagnation", "recommended_mode": "", "recommended_command": ""}
        result = _build_recommended_next_step(analysis, {"plan_only": "screenforge --plan-only"})
        assert result["recommended_mode"] == "plan_only"

    def test_dry_run_default_fallback(self):
        analysis = {"category": "execution_failure", "recommended_mode": "", "recommended_command": ""}
        result = _build_recommended_next_step(analysis, {"dry_run": "screenforge --dry-run"})
        assert result["recommended_mode"] == "dry_run"

    def test_uses_explicit_recommended_mode(self):
        analysis = {"category": "locator_resolution", "recommended_mode": "dry_run",
                    "recommended_command": "custom cmd"}
        result = _build_recommended_next_step(analysis, {})
        assert result["recommended_mode"] == "dry_run"
        assert result["recommended_command"] == "custom cmd"
