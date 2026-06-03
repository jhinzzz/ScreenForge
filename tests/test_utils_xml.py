"""Tests for utils/utils_xml.py — Android UI-tree compression.

Hermetic (no device). The key regression guard: the compressor must emit the
FULL resource-id (pkg:id/name), because uiautomator2's resourceId selector
matches the full id. A real-device smoke caught that stripping the prefix
produced ids that could never be located — silently breaking the agent's
#2-priority Android locator.
"""

import json

from utils.utils_xml import compress_android_xml

_XML = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" resource-id="com.android.settings:id/main">
    <node class="android.widget.AutoCompleteTextView"
          resource-id="com.android.settings:id/search_src_text"
          text="搜索设置项" clickable="true"/>
    <node class="android.widget.TextView"
          resource-id="com.android.settings:id/title"
          text="显示与亮度" clickable="true"/>
    <node class="android.widget.TextView"
          resource-id="com.example.app:id/dynamic_label_a1b2c3d4"
          text="Dynamic" clickable="true"/>
  </node>
</hierarchy>"""


def _elements(xml=_XML):
    return json.loads(compress_android_xml(xml)).get("ui_elements", [])


def test_emits_full_resource_id_not_stripped():
    els = _elements()
    search = next(e for e in els if e.get("text") == "搜索设置项")
    # MUST be the full pkg:id/name, matchable by uiautomator2 — not "search_src_text".
    assert search["id"] == "com.android.settings:id/search_src_text"


def test_full_id_kept_for_every_resource_id_element():
    for e in _elements():
        if "id" in e:
            assert ":id/" in e["id"], f"emitted a non-full resource-id: {e['id']!r}"


def test_id_short_hint_present_and_stripped():
    els = _elements()
    search = next(e for e in els if e.get("text") == "搜索设置项")
    # The optional short hint keeps the bare name (display/token economy only).
    assert search.get("id_short") == "search_src_text"


def test_id_short_strips_hash_suffix():
    els = _elements()
    dyn = next(e for e in els if e.get("text") == "Dynamic")
    # full id retains the hash (matchable), short hint strips the dynamic suffix.
    assert dyn["id"] == "com.example.app:id/dynamic_label_a1b2c3d4"
    assert dyn["id_short"] == "dynamic_label"


def test_malformed_xml_returns_empty_tree():
    assert json.loads(compress_android_xml("not valid xml <<<")) == {"ui_elements": []}


def test_text_and_clickable_preserved():
    els = _elements()
    row = next(e for e in els if e.get("text") == "显示与亮度")
    assert row["clickable"] is True
    assert row["class"] == "TextView"
