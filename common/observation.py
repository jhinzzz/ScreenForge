"""The ONE agent-facing observation envelope.

Every payload the external agent reads — inspect_ui, --action --json success and
engine_error, the MCP observation stash — composes this function. Adding a field
means editing THIS file and nothing else; that is the whole point. Two
constructors used to hand-assemble their own keys and drifted (the inspect
payload shipped the tree twice and two screenshots; case-memory reached the
agent only AFTER it had already acted).

Pure: no I/O, no device, no config reads — same contract as
cli/modes/action.py::build_success_payload.

Invariants:
  1. Additive only. Never shrink or truncate ui_tree — a trimmed tree makes the
     agent hit [E030] Ref not found and re-inspect, which costs MORE tokens.
  2. Honest empties. Absent data is {} / [] / "", never a guess (same rule as
     common/failure_diagnosis.py's below-threshold behavior).
  3. element_count is DERIVED here, never accepted from a caller, so it can
     never disagree with the tree it describes.
"""


def build_observation(
    *,
    ui_tree: dict,
    current_url: str = "",
    screenshot_base64: str = "",
    memory: dict | None = None,
    candidates: list[dict] | None = None,
) -> dict:
    elements = (ui_tree or {}).get("ui_elements") or []
    return {
        "ui_tree": ui_tree or {},
        "element_count": len(elements),
        "current_url": current_url,
        "screenshot_base64": screenshot_base64,
        # A HINT, never an instruction: what worked for this task last run. The
        # agent reads it alongside the live tree and decides whether to trust it.
        # We deliberately do NOT replay it (that is Midscene's XPath-cache route,
        # which silently clicks the wrong thing after a redesign).
        "memory": memory or {},
        # Elements matching the agent's plain-language phrase, best first. Empty
        # is a valid answer — below the similarity floor we return nothing rather
        # than a confident wrong guess.
        "candidates": candidates or [],
    }
