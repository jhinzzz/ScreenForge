"""inspect_ui turns a plain-language `intent` into ranked candidate locators.

This is the 听懂人话 half: the agent says what it wants in words and the payload
answers with elements it could mean. No intent -> empty list, zero cost.
"""

import cli.tool_protocol_handlers as tph
from common.tool_protocol import ToolRequest

_TREE_JSON = (
    '{"ui_elements":['
    '{"class":"Button","text":"登录","id":"com.app:id/login"},'
    '{"class":"Button","text":"注册","id":"com.app:id/reg"}]}'
)


class _FakeAdapter:
    def take_screenshot(self):
        return b"png"

    def teardown(self):
        pass


def _patch(monkeypatch):
    monkeypatch.setattr(tph, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(
        tph,
        "_capture_ui_state",
        lambda args, adapter, reporter, step_index: (_TREE_JSON, None),
    )


def _request(**extra) -> ToolRequest:
    return ToolRequest.model_validate(
        {"operation": "inspect_ui", "platform": "android", **extra}
    )


def test_no_intent_means_empty_candidates(monkeypatch):
    _patch(monkeypatch)
    payload = tph.build_inspect_ui_payload(_request())
    assert payload["candidates"] == []


def test_intent_returns_ranked_candidates_with_resource_id(monkeypatch):
    _patch(monkeypatch)
    payload = tph.build_inspect_ui_payload(_request(intent="登录"))
    assert payload["candidates"]
    top = payload["candidates"][0]
    assert top["text"] == "登录"
    assert top["locator"] == {"type": "resourceId", "value": "com.app:id/login"}


def test_unmatchable_intent_returns_empty_not_a_guess(monkeypatch):
    _patch(monkeypatch)
    payload = tph.build_inspect_ui_payload(_request(intent="完全无关的词句"))
    assert payload["candidates"] == []


def test_intent_does_not_shrink_the_tree(monkeypatch):
    # Invariant 1: candidates are ADDITIVE. The full tree must still ship, or
    # the agent hits [E030] and re-inspects — a net token loss.
    _patch(monkeypatch)
    payload = tph.build_inspect_ui_payload(_request(intent="登录"))
    assert payload["element_count"] == 2
    assert len(payload["ui_tree"]["ui_elements"]) == 2
