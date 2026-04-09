MODE_RUN = "run"
MODE_DOCTOR = "doctor"
MODE_PLAN_ONLY = "plan_only"
MODE_DRY_RUN = "dry_run"


def validate_mode_conflicts(
    doctor: bool,
    plan_only: bool,
    dry_run: bool,
) -> None:
    if doctor and (plan_only or dry_run):
        raise ValueError("doctor 模式不能与 plan-only 或 dry-run 同时使用")
    if plan_only and dry_run:
        raise ValueError("plan-only 与 dry-run 模式不能同时使用")


def resolve_execution_mode(
    doctor: bool,
    plan_only: bool,
    dry_run: bool,
) -> str:
    validate_mode_conflicts(
        doctor=doctor,
        plan_only=plan_only,
        dry_run=dry_run,
    )

    if doctor:
        return MODE_DOCTOR
    if plan_only:
        return MODE_PLAN_ONLY
    if dry_run:
        return MODE_DRY_RUN
    return MODE_RUN
