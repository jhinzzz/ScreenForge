"""Tests for cli/parser.py — argument parsing and validation."""

import pytest

from cli.parser import build_parser, validate_cli_args


class TestBuildParser:
    def test_goal_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--goal", "test login", "--platform", "web"])
        assert args.goal == "test login"
        assert args.platform == "web"

    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["--goal", "x"])
        assert args.platform == "web"
        assert args.env == "dev"
        assert args.max_steps == 15
        assert args.max_retries == 3
        assert args.vision is False
        assert args.json is False

    def test_action_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "--action", "click",
            "--locator-type", "css",
            "--locator-value", "#btn",
            "--platform", "web",
        ])
        assert args.action == "click"
        assert args.locator_type == "css"
        assert args.locator_value == "#btn"

    def test_workflow_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "--workflow", "flow.yaml",
            "--workflow-var", "USER=admin",
            "--workflow-var", "PASS=secret",
        ])
        assert args.workflow == "flow.yaml"
        assert args.workflow_var == ["USER=admin", "PASS=secret"]

    def test_mode_flags(self):
        parser = build_parser()
        args = parser.parse_args(["--goal", "x", "--plan-only"])
        assert args.plan_only is True
        assert args.dry_run is False
        assert args.doctor is False

    def test_resume_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--goal", "x", "--resume-run-id", "20260101_120000_abc123"])
        assert args.resume_run_id == "20260101_120000_abc123"


class TestValidateCliArgs:
    def _make_args(self, **overrides):
        parser = build_parser()
        defaults = parser.parse_args(["--goal", "test"])
        for k, v in overrides.items():
            setattr(defaults, k, v)
        return defaults

    def test_valid_goal(self):
        args = self._make_args()
        validate_cli_args(args)

    def test_goal_and_workflow_conflict(self):
        args = self._make_args(workflow="flow.yaml")
        with pytest.raises(ValueError, match="mutually exclusive"):
            validate_cli_args(args)

    def test_action_with_goal_conflict(self):
        args = self._make_args(action="click")
        with pytest.raises(ValueError, match="cannot be combined"):
            validate_cli_args(args)

    def test_no_goal_no_action_no_doctor(self):
        args = self._make_args(goal="")
        with pytest.raises(ValueError, match="Must provide"):
            validate_cli_args(args)

    def test_doctor_alone_valid(self):
        args = self._make_args(goal="", doctor=True)
        validate_cli_args(args)

    def test_mcp_server_with_goal_conflict(self):
        args = self._make_args(mcp_server=True)
        with pytest.raises(ValueError, match="--mcp-server cannot be combined"):
            validate_cli_args(args)

    def test_mcp_server_with_doctor_conflict(self):
        args = self._make_args(goal="", mcp_server=True, doctor=True)
        with pytest.raises(ValueError, match="--mcp-server cannot be combined"):
            validate_cli_args(args)

    def test_mcp_server_with_dry_run_conflict(self):
        args = self._make_args(goal="", mcp_server=True, dry_run=True)
        with pytest.raises(ValueError, match="--mcp-server cannot be combined"):
            validate_cli_args(args)

    def test_mcp_server_alone_valid(self):
        args = self._make_args(goal="", mcp_server=True)
        validate_cli_args(args)

    def test_tool_stdin_exclusive(self):
        args = self._make_args(tool_stdin=True)
        with pytest.raises(ValueError, match="--tool-stdin cannot be combined"):
            validate_cli_args(args)

    def test_tool_request_and_tool_stdin_conflict(self):
        args = self._make_args(goal="", tool_request="req.json", tool_stdin=True)
        with pytest.raises(ValueError, match="mutually exclusive"):
            validate_cli_args(args)

    def test_action_requires_locator(self):
        args = self._make_args(goal="", action="click", locator_type="", locator_value="")
        with pytest.raises(ValueError, match="require --locator-type"):
            validate_cli_args(args)

    def test_action_global_no_locator_needed(self):
        args = self._make_args(goal="", action="goto", extra_value="https://example.com")
        validate_cli_args(args)

    def test_action_extra_value_required(self):
        args = self._make_args(goal="", action="goto", extra_value="")
        with pytest.raises(ValueError, match="requires --extra-value"):
            validate_cli_args(args)

    def test_unsupported_action(self):
        args = self._make_args(goal="", action="fly", locator_type="css", locator_value="#x")
        with pytest.raises(ValueError, match="Unsupported action"):
            validate_cli_args(args)

    def test_workflow_var_format(self):
        args = self._make_args(goal="", workflow="flow.yaml", workflow_var=["INVALID"])
        with pytest.raises(ValueError, match="KEY=VALUE"):
            validate_cli_args(args)

    def test_demo_valid(self):
        args = self._make_args(goal="", demo=True)
        validate_cli_args(args)

    def test_playground_alone_valid(self):
        # Regression: --playground starts a standalone server (dispatch handles it
        # AFTER this validation, like --init/--demo) and needs no goal/action.
        # Before the fix it raised "Must provide --goal/--workflow/--action",
        # making the live-mirror entry point impossible to launch from the CLI.
        args = self._make_args(goal="", playground=True)
        validate_cli_args(args)

    def test_playground_with_port_valid(self):
        args = self._make_args(goal="", playground=True, playground_port=8000)
        validate_cli_args(args)
