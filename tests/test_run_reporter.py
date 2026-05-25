"""Tests for common/run_reporter.py — reporter lifecycle and failure classification."""

import json

import pytest

from common.run_reporter import (
    RunReporter,
    _build_failure_analysis,
    _build_pytest_asset,
)


@pytest.fixture
def reporter(tmp_path):
    return RunReporter(
        goal="test login",
        platform="web",
        env_name="dev",
        output_script_path="test_cases/web/test_auto.py",
        base_dir=str(tmp_path),
        execution_mode="run",
    )


class TestRunReporterInit:
    def test_creates_run_directory(self, reporter):
        assert reporter.run_dir.exists()

    def test_creates_summary_file(self, reporter):
        summary_file = reporter.run_dir / "summary.json"
        assert summary_file.exists()
        data = json.loads(summary_file.read_text())
        assert data["goal"] == "test login"
        assert data["platform"] == "web"
        assert data["status"] == "running"

    def test_creates_artifacts_file(self, reporter):
        artifacts_file = reporter.run_dir / "artifacts.json"
        assert artifacts_file.exists()
        data = json.loads(artifacts_file.read_text())
        assert "generated_script" in data

    def test_run_id_format(self, reporter):
        parts = reporter.run_id.split("_")
        assert len(parts) == 3
        assert len(parts[0]) == 8 and parts[0].isdigit()  # YYYYMMDD
        assert len(parts[1]) == 6 and parts[1].isdigit()  # HHMMSS
        assert len(parts[2]) == 8  # UUID prefix

    def test_execution_mode_stored(self, reporter):
        summary_file = reporter.run_dir / "summary.json"
        data = json.loads(summary_file.read_text())
        assert data["execution_mode"] == "run"


class TestRunReporterEmitEvent:
    def test_appends_to_steps_file(self, reporter):
        reporter.emit_event("test_event", foo="bar")
        steps_file = reporter.run_dir / "steps.jsonl"
        assert steps_file.exists()
        lines = steps_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "test_event"
        assert record["foo"] == "bar"
        assert record["run_id"] == reporter.run_id

    def test_multiple_events(self, reporter):
        reporter.emit_event("event_1")
        reporter.emit_event("event_2")
        reporter.emit_event("event_3")
        steps_file = reporter.run_dir / "steps.jsonl"
        lines = steps_file.read_text().strip().split("\n")
        assert len(lines) == 3


class TestRunReporterSaveScreenshot:
    def test_saves_png(self, reporter):
        from pathlib import Path

        img = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        path = reporter.save_screenshot(img, step_index=1)
        assert path != ""
        assert path.endswith(".png")
        assert Path(path).exists()
        assert Path(path).read_bytes() == img

    def test_empty_bytes_returns_empty(self, reporter):
        assert reporter.save_screenshot(b"", step_index=1) == ""


class TestRunReporterFinalize:
    def test_finalize_sets_status(self, reporter):
        reporter.finalize(status="success", exit_code=0, steps_executed=5)
        summary_file = reporter.run_dir / "summary.json"
        data = json.loads(summary_file.read_text())
        assert data["status"] == "success"
        assert data["exit_code"] == 0
        assert data["steps_executed"] == 5
        assert data["finished_at"] is not None

    def test_finalize_creates_pytest_manifest(self, reporter):
        reporter.finalize(status="failed", exit_code=1, steps_executed=3, last_error="timeout")
        manifest = reporter.run_dir / "pytest_replay.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert data["run_id"] == reporter.run_id
        assert data["status"] == "failed"

    def test_finalize_idempotent(self, reporter):
        reporter.finalize(status="success", exit_code=0, steps_executed=1)
        reporter.finalize(status="failed", exit_code=1, steps_executed=2)
        summary_file = reporter.run_dir / "summary.json"
        data = json.loads(summary_file.read_text())
        assert data["status"] == "success"  # first call wins

    def test_failure_analysis_present_on_error(self, reporter):
        reporter.finalize(status="failed", exit_code=1, steps_executed=2, last_error="element not found")
        summary_file = reporter.run_dir / "summary.json"
        data = json.loads(summary_file.read_text())
        assert data["failure_analysis"] is not None
        assert data["failure_analysis"]["category"] == "locator_resolution"

    def test_failure_analysis_generic_error(self, reporter):
        reporter.finalize(status="failed", exit_code=1, steps_executed=2, last_error="unknown failure")
        summary_file = reporter.run_dir / "summary.json"
        data = json.loads(summary_file.read_text())
        assert data["failure_analysis"] is not None
        assert data["failure_analysis"]["category"] == "execution_failure"

    def test_failure_analysis_none_on_success(self, reporter):
        reporter.finalize(status="success", exit_code=0, steps_executed=5)
        summary_file = reporter.run_dir / "summary.json"
        data = json.loads(summary_file.read_text())
        assert data["failure_analysis"] is None


class TestBuildFailureAnalysis:
    def _build(self, last_error="", status="failed", exit_code=1, steps_executed=3):
        return _build_failure_analysis(
            run_id="test_run",
            platform="web",
            execution_mode="run",
            status=status,
            exit_code=exit_code,
            steps_executed=steps_executed,
            last_error=last_error,
            pytest_asset={"resume_commands": {}, "replay_ready": False},
        )

    def test_success_returns_none(self):
        result = self._build(status="success", exit_code=0, last_error="")
        assert result is None

    def test_locator_resolution(self):
        result = self._build(last_error="element not found on page")
        assert result["category"] == "locator_resolution"

    def test_not_interactable(self):
        result = self._build(last_error="button is not interactable")
        assert result["category"] == "locator_resolution"

    def test_environment_restricted(self):
        result = self._build(last_error="Operation not permitted")
        assert result["category"] == "environment_restricted"
        assert result["retryable"] is False

    def test_permission_denied(self):
        result = self._build(last_error="permission denied accessing device")
        assert result["category"] == "environment_restricted"

    def test_stagnation_circuit_breaker(self):
        result = self._build(last_error="circuit breaker triggered after 3 retries")
        assert result["category"] == "stagnation"

    def test_stagnation_consecutive_failures(self):
        result = self._build(last_error="consecutive failures exceeded limit")
        assert result["category"] == "stagnation"

    def test_configuration_error(self):
        result = self._build(last_error="configuration validation failed for api_key")
        assert result["category"] == "configuration"
        assert result["retryable"] is False

    def test_startup_stage_zero_steps(self):
        result = self._build(last_error="some unknown error", steps_executed=0)
        assert result["stage"] == "startup"

    def test_generic_execution_failure(self):
        result = self._build(last_error="something went wrong")
        assert result["category"] == "execution_failure"
        assert result["retryable"] is True


class TestBuildPytestAsset:
    def test_basic_structure(self, tmp_path):
        script = tmp_path / "test_auto.py"
        script.write_text("# test")
        asset = _build_pytest_asset(str(script), run_id="r1", platform="web")
        assert asset["exists"] is True
        assert asset["replay_ready"] is True
        assert "pytest" in asset["pytest_command"]

    def test_nonexistent_script(self):
        asset = _build_pytest_asset("/nonexistent/test.py", run_id="r1", platform="web")
        assert asset["exists"] is False
        assert asset["replay_ready"] is False

    def test_resume_commands_populated(self):
        asset = _build_pytest_asset("test.py", run_id="r1", platform="web")
        cmds = asset["resume_commands"]
        assert "plan_only" in cmds
        assert "dry_run" in cmds
        assert "run" in cmds
        assert "doctor" in cmds

    def test_resume_commands_empty_on_blank_inputs(self):
        asset = _build_pytest_asset("test.py", run_id="", platform="")
        assert asset["resume_commands"] == {}
