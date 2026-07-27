"""The MCP tool result must not carry the payload twice.

structuredContent IS the payload. content[0].text used to be a second full
json.dumps of the same dict, doubling every response — on a payload already
carrying a UI tree and a screenshot, that is the single largest avoidable
cost on the wire. content stays present (MCP requires it) but summarizes.
"""

import json

from common.mcp_server import _build_tool_result


def _payload(ok=True):
    return {
        "ok": ok,
        "operation": "inspect_ui",
        "element_count": 2,
        "ui_tree": {"ui_elements": [{"text": "登录"}, {"text": "注册"}]},
        "screenshot_base64": "QUJD" * 500,
    }


def test_structured_content_is_the_full_payload():
    payload = _payload()
    result = _build_tool_result(payload)
    assert result["structuredContent"] == payload


def test_text_content_does_not_duplicate_the_payload():
    payload = _payload()
    result = _build_tool_result(payload)
    text = result["content"][0]["text"]
    assert "QUJD" * 500 not in text
    assert len(text) < 200


def test_text_content_is_present_and_non_empty():
    # MCP requires a non-empty content array.
    result = _build_tool_result(_payload())
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"].strip()


def test_text_summary_names_the_operation():
    result = _build_tool_result(_payload())
    assert "inspect_ui" in result["content"][0]["text"]


def test_is_error_tracks_ok():
    assert _build_tool_result(_payload(ok=True))["isError"] is False
    assert _build_tool_result(_payload(ok=False))["isError"] is True


def test_error_payload_surfaces_the_error_text():
    result = _build_tool_result({"ok": False, "operation": "execute", "error": "boom"})
    assert "boom" in result["content"][0]["text"]


def test_summary_is_not_valid_json_payload():
    # Guard against someone "restoring" the dump: the summary must not parse
    # back into the payload dict.
    text = _build_tool_result(_payload())["content"][0]["text"]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return
    assert not isinstance(parsed, dict) or "ui_tree" not in parsed
