"""Tests for cli/dispatch.py — execution routing logic."""

from types import SimpleNamespace
from unittest.mock import patch

from cli.dispatch import _dispatch_execution
from common.runtime_modes import MODE_DOCTOR, MODE_DRY_RUN, MODE_PLAN_ONLY, MODE_RUN


def _make_args(**overrides):
    defaults = {
        "workflow": "",
        "action": "",
        "goal": "test goal",
        "platform": "web",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestDispatchExecution:
    @patch("cli.dispatch.run_doctor_mode", return_value=0)
    def test_doctor_mode_dispatches(self, mock_doctor):
        args = _make_args()
        result = _dispatch_execution(args, MODE_DOCTOR, "out.py", "", {})
        mock_doctor.assert_called_once_with(args, "out.py")
        assert result == 0

    @patch("cli.dispatch.run_plan_only_mode", return_value=0)
    def test_goal_plan_only_dispatches(self, mock_plan):
        args = _make_args()
        result = _dispatch_execution(args, MODE_PLAN_ONLY, "out.py", "ctx", {})
        mock_plan.assert_called_once_with(args, "out.py", "ctx", {})
        assert result == 0

    @patch("cli.dispatch.run_dry_run_mode", return_value=0)
    def test_goal_dry_run_dispatches(self, mock_dry):
        args = _make_args()
        result = _dispatch_execution(args, MODE_DRY_RUN, "out.py", "ctx", {})
        mock_dry.assert_called_once_with(args, "out.py", "ctx", {})
        assert result == 0

    @patch("cli.dispatch.run_default_mode", return_value=0)
    def test_goal_run_dispatches(self, mock_default):
        args = _make_args()
        result = _dispatch_execution(args, MODE_RUN, "out.py", "ctx", {})
        mock_default.assert_called_once_with(args, "out.py", "ctx", {})
        assert result == 0

    @patch("cli.dispatch.run_workflow_plan_only_mode", return_value=0)
    def test_workflow_plan_only_dispatches(self, mock_wf_plan):
        args = _make_args(workflow="flow.yaml")
        result = _dispatch_execution(args, MODE_PLAN_ONLY, "out.py", "", {})
        mock_wf_plan.assert_called_once_with(args, "out.py", {})
        assert result == 0

    @patch("cli.dispatch.run_workflow_dry_run_mode", return_value=0)
    def test_workflow_dry_run_dispatches(self, mock_wf_dry):
        args = _make_args(workflow="flow.yaml")
        result = _dispatch_execution(args, MODE_DRY_RUN, "out.py", "", {})
        mock_wf_dry.assert_called_once_with(args, "out.py", {})
        assert result == 0

    @patch("cli.dispatch.run_workflow_default_mode", return_value=0)
    def test_workflow_run_dispatches(self, mock_wf_default):
        args = _make_args(workflow="flow.yaml")
        result = _dispatch_execution(args, MODE_RUN, "out.py", "", {})
        mock_wf_default.assert_called_once_with(args, "out.py", {})
        assert result == 0

    @patch("cli.dispatch.run_action_plan_only_mode", return_value=0)
    def test_action_plan_only_dispatches(self, mock_act_plan):
        args = _make_args(action="click")
        result = _dispatch_execution(args, MODE_PLAN_ONLY, "out.py", "", {})
        mock_act_plan.assert_called_once_with(args, "out.py", {})
        assert result == 0

    @patch("cli.dispatch.run_action_dry_run_mode", return_value=0)
    def test_action_dry_run_dispatches(self, mock_act_dry):
        args = _make_args(action="click")
        result = _dispatch_execution(args, MODE_DRY_RUN, "out.py", "", {})
        mock_act_dry.assert_called_once_with(args, "out.py", {})
        assert result == 0

    @patch("cli.dispatch.run_action_default_mode", return_value=0)
    def test_action_run_dispatches(self, mock_act_default):
        args = _make_args(action="click")
        result = _dispatch_execution(args, MODE_RUN, "out.py", "", {})
        mock_act_default.assert_called_once_with(args, "out.py", {}, shared_adapter_manager=None)
        assert result == 0

    @patch("cli.dispatch.run_default_mode", return_value=1)
    def test_propagates_exit_code(self, mock_default):
        args = _make_args()
        result = _dispatch_execution(args, MODE_RUN, "out.py", "ctx", {})
        assert result == 1
