"""Shorthand CLI preprocessor — expands concise commands to full flag format.

Transforms:
    screenforge click "Login"           → --action click --locator-type text --locator-value Login
    screenforge click "#email"          → --action click --locator-type css --locator-value #email
    screenforge click "@3"              → --action click --locator-type ref --locator-value @3
    screenforge input "#email" "admin"  → --action input --locator-type css --locator-value #email --extra-value admin
    screenforge goto "https://..."      → --action goto --extra-value https://...
    screenforge press "Enter"           → --action press --extra-value Enter
    screenforge swipe up                → --action swipe --extra-value up
    screenforge inspect                 → --tool-stdin (with inspect_ui on stdin)
    screenforge demo                    → --demo

Passthrough: any argv starting with -- is left untouched (legacy flag mode).
"""

from common.capabilities import GLOBAL_ACTIONS, SUPPORTED_ACTIONS

SHORTHAND_COMMANDS = set(SUPPORTED_ACTIONS) | {"inspect", "demo"}

ACTIONS_WITH_EXTRA_ONLY = GLOBAL_ACTIONS  # goto, press, swipe — no locator needed


def _detect_locator_type(value: str) -> str:
    if value.startswith("@"):
        return "ref"
    if value.startswith(("#", ".", "[")):
        return "css"
    return "text"


def preprocess_argv(argv: list[str]) -> list[str]:
    """If argv[1] is a known shorthand command (no -- prefix), expand it.
    Returns the transformed argv list ready for argparse."""
    if len(argv) < 2:
        return argv

    cmd = argv[1]

    if cmd.startswith("-"):
        return argv

    if cmd not in SHORTHAND_COMMANDS:
        return argv

    if cmd == "demo":
        return [argv[0], "--demo"] + argv[2:]

    if cmd == "inspect":
        return [argv[0], "--tool-stdin"] + argv[2:]

    rest = argv[2:]
    flags_from_rest = []
    positional = []
    i = 0
    while i < len(rest):
        if rest[i].startswith("-"):
            flags_from_rest.append(rest[i])
            # Grab the flag's value if it's not another flag
            if i + 1 < len(rest) and not rest[i + 1].startswith("-"):
                flags_from_rest.append(rest[i + 1])
                i += 2
            else:
                i += 1
        else:
            positional.append(rest[i])
            i += 1

    expanded = [argv[0], "--action", cmd]

    if cmd in ACTIONS_WITH_EXTRA_ONLY:
        if positional:
            expanded += ["--extra-value", positional[0]]
            positional = positional[1:]
    else:
        if positional:
            locator_val = positional[0]
            locator_type = _detect_locator_type(locator_val)
            expanded += ["--locator-type", locator_type, "--locator-value", locator_val]
            positional = positional[1:]
        if positional:
            expanded += ["--extra-value", positional[0]]
            positional = positional[1:]

    expanded += flags_from_rest

    if "--platform" not in flags_from_rest:
        expanded += ["--platform", "web"]

    return expanded


def inject_inspect_stdin() -> bool:
    """For 'screenforge inspect', we need to feed JSON to stdin.
    Returns True if stdin was injected (caller should handle)."""
    return False  # handled via dispatch, not actual stdin injection
