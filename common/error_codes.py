"""Single source of truth for agent-facing error codes.

Both the stderr log (`log.error(format_log("E037"))`) and the `--action --json`
failure payload read message + fix from this one table, so the two channels can
never drift. Scope is deliberately narrow: only the locate/action codes an agent
hits on the `--action` path. Connection codes (E04x/E05x) and `--goal`-only codes
(E02x stagnation / circuit-breaker / max-steps) are intentionally NOT here — this
iteration does not touch those paths.
"""

# code -> (message, fix)
ERROR_CODES: dict[str, tuple[str, str]] = {
    "E030": (
        "Ref not found in cache.",
        "Run inspect_ui first to refresh the element cache.",
    ),
    "E031": (
        "Unsupported action type.",
        "See `screenforge --capabilities` for the supported action list.",
    ),
    "E032": (
        "Element action missing locator_type.",
        "Provide locator_type (css/text/resourceId/description).",
    ),
    "E033": (
        "Element locator is empty after resolution.",
        "Verify the target exists on the current page via inspect_ui.",
    ),
    "E035": (
        "AI returned empty action type.",
        "Check that MODEL_NAME supports structured JSON output.",
    ),
    "E036": (
        "Ref has no stable locator (only coordinates).",
        "Re-inspect; use a text/css locator instead of a coordinate-only ref.",
    ),
    "E037": (
        "Element could not be located for the action.",
        "Re-inspect, scroll the target into view, or add --vision.",
    ),
    "E038": (
        "Element located but the action failed or was blocked.",
        "Check for overlays; ensure the element is enabled and in the viewport.",
    ),
}

_GENERIC = (
    "Action failed.",
    "Re-inspect via inspect_ui and adjust strategy.",
)


def lookup(code: str) -> tuple[str, str]:
    """Return (message, fix) for a code; unknown codes get a generic, non-raising fallback."""
    return ERROR_CODES.get(code, _GENERIC)


def format_log(code: str) -> str:
    """Format a code for stderr: '[E037] <message> Fix: <fix>'."""
    msg, fix = lookup(code)
    return f"[{code}] {msg} Fix: {fix}"
