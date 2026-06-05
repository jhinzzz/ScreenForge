"""Contract tests for the --action --json failure payload.

These pin the agent-facing JSON shape without a device by calling the payload
builder directly. The branch logic (engine_error enriches with diagnosis +
ui_tree; assertion_failed stays a bare verdict) is the contract an agent
branches on, so it must be locked.
"""

from cli.modes.action import build_failure_payload


def test_engine_error_payload_has_diagnosis_and_uitree():
    ui_tree = {"ui_elements": [{"ref": "@1", "text": "Log in", "clickable": True}]}
    payload = build_failure_payload(
        action_name="click:Login",
        platform="web",
        assertion_failed=False,
        error_code="E037",
        locator_value="Login",
        ui_tree=ui_tree,
        current_url="https://example.com/login",
    )
    assert payload["ok"] is False
    assert payload["result"] == "engine_error"
    assert payload["error_code"] == "E037"
    assert "Re-inspect" in payload["fix"]  # E037's table fix text, not a placeholder
    assert payload["candidates"][0]["text"] == "Log in"
    assert payload["ui_tree"] == ui_tree
    assert payload["element_count"] == 1
    assert payload["current_url"] == "https://example.com/login"


def test_assertion_failed_payload_is_bare_verdict():
    payload = build_failure_payload(
        action_name="assert_exist:Dashboard",
        platform="web",
        assertion_failed=True,
        error_code="",
        locator_value="Dashboard",
        ui_tree={"ui_elements": []},
        current_url="https://example.com",
    )
    assert payload["ok"] is False
    assert payload["result"] == "assertion_failed"
    assert payload["assertion_failed"] is True
    # A verdict carries no did-you-mean, no page, no retry bait.
    assert "candidates" not in payload
    assert "ui_tree" not in payload
    assert "recommended_next_step" not in payload
    assert "current_url" not in payload
    assert "element_count" not in payload
