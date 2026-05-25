"""Tests for common/runtime_modes.py — mode resolution and conflict detection."""

import pytest

from common.runtime_modes import (
    MODE_DOCTOR,
    MODE_DRY_RUN,
    MODE_PLAN_ONLY,
    MODE_RUN,
    resolve_execution_mode,
    validate_mode_conflicts,
)


class TestResolveExecutionMode:
    def test_defaults_to_run(self):
        assert resolve_execution_mode(doctor=False, plan_only=False, dry_run=False) == MODE_RUN

    def test_doctor_flag(self):
        assert resolve_execution_mode(doctor=True, plan_only=False, dry_run=False) == MODE_DOCTOR

    def test_plan_only_flag(self):
        assert resolve_execution_mode(doctor=False, plan_only=True, dry_run=False) == MODE_PLAN_ONLY

    def test_dry_run_flag(self):
        assert resolve_execution_mode(doctor=False, plan_only=False, dry_run=True) == MODE_DRY_RUN

    def test_doctor_with_plan_only_raises(self):
        with pytest.raises(ValueError):
            resolve_execution_mode(doctor=True, plan_only=True, dry_run=False)

    def test_plan_only_with_dry_run_raises(self):
        with pytest.raises(ValueError):
            resolve_execution_mode(doctor=False, plan_only=True, dry_run=True)


class TestValidateModeConflicts:
    def test_doctor_with_plan_only_raises(self):
        with pytest.raises(ValueError, match="--doctor cannot be combined"):
            validate_mode_conflicts(doctor=True, plan_only=True, dry_run=False)

    def test_doctor_with_dry_run_raises(self):
        with pytest.raises(ValueError, match="--doctor cannot be combined"):
            validate_mode_conflicts(doctor=True, plan_only=False, dry_run=True)

    def test_plan_only_with_dry_run_raises(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            validate_mode_conflicts(doctor=False, plan_only=True, dry_run=True)

    def test_no_flags_passes(self):
        validate_mode_conflicts(doctor=False, plan_only=False, dry_run=False)

    def test_single_flags_pass(self):
        validate_mode_conflicts(doctor=True, plan_only=False, dry_run=False)
        validate_mode_conflicts(doctor=False, plan_only=True, dry_run=False)
        validate_mode_conflicts(doctor=False, plan_only=False, dry_run=True)
