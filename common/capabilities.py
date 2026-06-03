from common.runtime_modes import MODE_DOCTOR, MODE_DRY_RUN, MODE_PLAN_ONLY, MODE_RUN

SUPPORTED_PLATFORMS = ("android", "ios", "web")
SUPPORTED_ACTIONS = (
    "goto",
    "click",
    "long_click",
    "hover",
    "input",
    "swipe",
    "press",
    "assert_exist",
    "assert_text_equals",
)
GLOBAL_ACTIONS = {"goto", "swipe", "press"}
ACTIONS_REQUIRING_EXTRA_VALUE = {"goto", "input", "assert_text_equals"}
CONTROL_PLANES = ("goal", "workflow", "action", "doctor")
EXECUTION_MODES = (MODE_RUN, MODE_DOCTOR, MODE_PLAN_ONLY, MODE_DRY_RUN)

# Which locator_type values actually resolve on each platform. This mirrors the
# real executor / UI-compressor behavior, NOT aspiration:
#   - web: compress_web_dom emits ref/bbox; LocatorBuilder maps css/text/desc.
#   - android: utils_xml emits resource-id/text/content-desc (no ref/bbox).
#   - ios: utils_ios maps text/desc -> label/name (no ref/bbox); resourceId->name.
# An agent should read this instead of assuming `ref` works everywhere.
LOCATORS_BY_PLATFORM = {
    "web": ["css", "ref", "text", "description"],
    "android": ["resourceId", "text", "description"],
    "ios": ["text", "description"],
}

# Platform-gated location features. ref/bbox and the VLM visual fallback are
# web-only (mobile UI-tree compressors don't emit ref/bbox, and the visual
# fallback in executor.py is gated on platform == "web").
FEATURES_BY_PLATFORM = {
    "ref_bbox": ["web"],
    "screenshot_annotation": ["web"],
    "visual_fallback": ["web"],
}


def get_capabilities_payload() -> dict:
    return {
        "platforms": list(SUPPORTED_PLATFORMS),
        "execution_modes": list(EXECUTION_MODES),
        "control_planes": list(CONTROL_PLANES),
        "supported_actions": list(SUPPORTED_ACTIONS),
        "global_actions": sorted(GLOBAL_ACTIONS),
        "actions_requiring_extra_value": sorted(ACTIONS_REQUIRING_EXTRA_VALUE),
        "locators": {p: list(v) for p, v in LOCATORS_BY_PLATFORM.items()},
        "locator_priority": ["css", "resourceId", "text", "description"],
        "features": {f: list(v) for f, v in FEATURES_BY_PLATFORM.items()},
        "supports": {
            "doctor": True,
            "resume": True,
            "workflow": True,
            "workflow_vars": True,
            "action": True,
            "inspect_ui": True,
            "case_memory": True,
            "run_assets": True,
            "load_run": True,
            "tool_request": True,
            "tool_stdin": True,
            "mcp_server": True,
            "json_events": True,
            "goal_cli_human_mode_only": True,
        },
        "docs": {
            "capability_matrix": "docs/capability-matrix.md",
            "agent_guide": "docs/agent_guide.md",
        },
    }
