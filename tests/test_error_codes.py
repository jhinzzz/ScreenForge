"""Tests for common/error_codes.py — the single source of truth for the
agent-facing [E0xx] codes. Both stderr logs and the --action --json payload
read message+fix from here, so they can never drift apart again.
"""

from common.error_codes import ERROR_CODES, format_log, lookup


def test_known_code_returns_message_and_fix():
    msg, fix = lookup("E037")
    assert "locate" in msg.lower()
    assert fix  # non-empty actionable fix


def test_unknown_code_returns_generic_fallback_without_raising():
    msg, fix = lookup("E999")
    assert msg
    assert fix
    assert "inspect_ui" in fix.lower()


def test_format_log_shape():
    line = format_log("E037")
    assert line.startswith("[E037] ")
    assert "Fix: " in line


def test_all_codes_have_nonempty_message_and_fix():
    for code, (msg, fix) in ERROR_CODES.items():
        assert msg.strip(), f"{code} has empty message"
        assert fix.strip(), f"{code} has empty fix"
