"""Tests for utils/utils_ios.py — iOS WDA XML compression.

Hermetic (no simulator/device). Establishes the offline baseline the HANDOFF
called for, and pins the cross-platform contract: a disabled control is reported
with the SAME `disabled: true` key as Android (utils_xml.py) and Web
(utils_web.py), so the single LLM brain sees one vocabulary for "can't interact"
across every platform — not `enabled:false` on iOS and `disabled:true` elsewhere.
"""

import json

from utils.utils_ios import compress_ios_xml

_XML = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="App" label="App" enabled="true" visible="true">
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="submit" label="提交"
      enabled="false" visible="true" accessible="true"/>
  <XCUIElementTypeButton type="XCUIElementTypeButton" name="cancel" label="取消"
      enabled="true" visible="true" accessible="true"/>
  <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" label="标题"
      enabled="true" visible="true"/>
</XCUIElementTypeApplication>"""


def _elements(xml=_XML):
    return json.loads(compress_ios_xml(xml)).get("ui_elements", [])


def test_compress_returns_visible_elements():
    els = _elements()
    labels = {e.get("label") for e in els}
    assert "提交" in labels and "取消" in labels and "标题" in labels


def test_disabled_control_uses_disabled_true_key():
    """Cross-platform unification: a disabled iOS control must carry `disabled:
    true` — the same key Android/Web use — NOT the legacy `enabled: false`."""
    els = _elements()
    submit = next((e for e in els if e.get("label") == "提交"), None)
    assert submit is not None, "disabled button should still be emitted (for assertions)"
    assert submit.get("disabled") is True, (
        "disabled iOS control must use the unified `disabled:true` key (was `enabled:false`)"
    )
    assert "enabled" not in submit, (
        "legacy `enabled` key still emitted — diverges from Android/Web schema"
    )


def test_enabled_control_has_no_disabled_flag():
    # Over-correction guard: an enabled control carries neither key.
    els = _elements()
    cancel = next((e for e in els if e.get("label") == "取消"), None)
    assert cancel is not None
    assert cancel.get("disabled") is not True
    assert "enabled" not in cancel


def test_invisible_node_dropped():
    xml = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" label="App" visible="true">
  <XCUIElementTypeButton type="XCUIElementTypeButton" label="hidden"
      enabled="true" visible="false"/>
</XCUIElementTypeApplication>"""
    assert all(e.get("label") != "hidden" for e in _elements(xml))


def test_malformed_xml_returns_empty_tree():
    assert json.loads(compress_ios_xml("not valid <<<")) == {"ui_elements": []}
