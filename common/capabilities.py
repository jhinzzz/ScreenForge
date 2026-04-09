from pathlib import Path

from common.runtime_modes import MODE_DOCTOR, MODE_DRY_RUN, MODE_PLAN_ONLY, MODE_RUN


SUPPORTED_PLATFORMS = ("android", "ios", "web")
SUPPORTED_ACTIONS = (
    "click",
    "long_click",
    "hover",
    "input",
    "swipe",
    "press",
    "assert_exist",
    "assert_text_equals",
)
GLOBAL_ACTIONS = {"swipe", "press"}
ACTIONS_REQUIRING_EXTRA_VALUE = {"input", "assert_text_equals"}
CONTROL_PLANES = ("goal", "workflow", "action", "doctor")
EXECUTION_MODES = (MODE_RUN, MODE_DOCTOR, MODE_PLAN_ONLY, MODE_DRY_RUN)


def get_capabilities_payload() -> dict:
    project_root = Path(__file__).resolve().parent.parent
    return {
        "platforms": list(SUPPORTED_PLATFORMS),
        "execution_modes": list(EXECUTION_MODES),
        "control_planes": list(CONTROL_PLANES),
        "supported_actions": list(SUPPORTED_ACTIONS),
        "global_actions": sorted(GLOBAL_ACTIONS),
        "actions_requiring_extra_value": sorted(ACTIONS_REQUIRING_EXTRA_VALUE),
        "supports": {
            "doctor": True,
            "resume": True,
            "workflow": True,
            "workflow_vars": True,
            "action": True,
            "run_assets": True,
            "load_run": True,
            "tool_request": True,
            "tool_stdin": True,
            "mcp_server": True,
            "json_events": True,
        },
        "docs": {
            "capability_matrix": str(project_root / "docs" / "capability-matrix.md"),
            "agent_guide": str(project_root / "docs" / "agent_guide.md"),
        },
    }
