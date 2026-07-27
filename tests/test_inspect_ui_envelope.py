"""inspect_ui must ship ONE tree and AT MOST ONE screenshot, --vision-gated.

The old payload sent the tree twice (ui_json + ui_tree) and two full PNGs, and
captured a screenshot even with --vision off — the biggest single token sink on
the agent-facing path. These tests pin the deletions so they can't creep back.
"""

import cli.tool_protocol_handlers as tph
from common.tool_protocol import ToolRequest

_TREE_JSON = '{"ui_elements":[{"text":"登录","id":"login-btn"}]}'


class _SpyAdapter:
    def __init__(self):
        self.screenshot_calls = 0
        self.teardown_called = False

    def take_screenshot(self):
        self.screenshot_calls += 1
        return b"\x89PNG\r\n\x1a\n-not-a-real-png"

    def teardown(self):
        self.teardown_called = True


def _request(vision: bool) -> ToolRequest:
    return ToolRequest.model_validate(
        {"operation": "inspect_ui", "platform": "android", "vision": vision}
    )


def _patch(monkeypatch, adapter, screenshot_base64):
    monkeypatch.setattr(tph, "_connect_adapter", lambda args, reporter: adapter)
    monkeypatch.setattr(
        tph,
        "_capture_ui_state",
        lambda args, current_adapter, reporter, step_index: (_TREE_JSON, screenshot_base64),
    )


def test_ui_json_key_is_gone(monkeypatch):
    adapter = _SpyAdapter()
    _patch(monkeypatch, adapter, None)
    payload = tph.build_inspect_ui_payload(_request(vision=False))
    assert "ui_json" not in payload
    assert payload["ui_tree"]["ui_elements"][0]["text"] == "登录"
    assert payload["element_count"] == 1


def test_annotated_screenshot_key_is_gone(monkeypatch):
    adapter = _SpyAdapter()
    _patch(monkeypatch, adapter, "QUJD")
    payload = tph.build_inspect_ui_payload(_request(vision=True))
    assert "annotated_screenshot_base64" not in payload


def test_vision_off_captures_no_screenshot(monkeypatch):
    # The bug: a fallback branch grabbed a screenshot even with --vision off,
    # defeating the gate in cli/shared.py and shipping ~50k+ tokens of base64.
    adapter = _SpyAdapter()
    _patch(monkeypatch, adapter, None)
    payload = tph.build_inspect_ui_payload(_request(vision=False))
    assert payload["screenshot_base64"] == ""
    assert adapter.screenshot_calls == 0


def test_vision_on_ships_exactly_one_image(monkeypatch):
    adapter = _SpyAdapter()
    _patch(monkeypatch, adapter, "QUJD")
    payload = tph.build_inspect_ui_payload(_request(vision=True))
    assert payload["screenshot_base64"] != ""
    image_keys = [k for k in payload if "screenshot" in k]
    assert image_keys == ["screenshot_base64"]


def test_payload_key_set_is_exact(monkeypatch):
    adapter = _SpyAdapter()
    _patch(monkeypatch, adapter, None)
    payload = tph.build_inspect_ui_payload(_request(vision=False))
    assert set(payload) == {
        "ok", "operation", "exit_code", "platform", "env",
        "ui_tree", "element_count", "current_url", "screenshot_base64",
        "memory", "candidates",
    }


def test_adapter_is_still_torn_down(monkeypatch):
    adapter = _SpyAdapter()
    _patch(monkeypatch, adapter, None)
    tph.build_inspect_ui_payload(_request(vision=False))
    assert adapter.teardown_called is True
