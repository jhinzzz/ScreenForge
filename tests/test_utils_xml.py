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


# --- disabled controls (enabled="false") -----------------------------------
# Mirrors the web compressor contract (utils_web.py): a control the user can't
# interact with must be reported clickable:false so the LLM brain doesn't tap a
# dead button and hang on the timeout — but still emitted (with disabled:true) so
# its existence/disabled-state remains assertable. Android exposes this via the
# `enabled` attribute, which the compressor previously ignored entirely.

_XML_DISABLED = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.Button" resource-id="com.x:id/ok"
        text="提交" clickable="true" enabled="false"/>
  <node class="android.widget.Button" resource-id="com.x:id/cancel"
        text="取消" clickable="true" enabled="true"/>
  <node class="android.widget.TextView" resource-id="com.x:id/hint"
        text="表单未填完" clickable="false" enabled="false"/>
</hierarchy>"""


def test_disabled_clickable_node_marked_not_clickable():
    els = _elements(_XML_DISABLED)
    ok = next((e for e in els if e.get("text") == "提交"), None)
    assert ok is not None, "disabled button should still be emitted (for assertions)"
    # Android omits clickable when false (only clickable:true is emitted), so the
    # disabled button must NOT carry a truthy clickable — the LLM keys on it.
    assert ok.get("clickable") is not True, (
        "disabled (enabled=false) button reported clickable — the LLM will tap it and hang"
    )
    assert ok.get("disabled") is True, "disabled control should carry an explicit disabled flag"


def test_enabled_clickable_node_stays_clickable():
    # Over-correction guard: a normal enabled button keeps clickable:true.
    els = _elements(_XML_DISABLED)
    cancel = next((e for e in els if e.get("text") == "取消"), None)
    assert cancel is not None and cancel.get("clickable") is True
    assert cancel.get("disabled") is not True


def test_disabled_short_numeric_control_still_emitted():
    """Regression for the filter-order trap: a disabled control with short numeric
    text (e.g. a disabled "+5" stepper) must NOT be dropped by the numeric-noise
    text filter. The filter only fires for non-clickable text, and a disabled
    control is now clickable=False — so without guarding it, the disabled control
    vanishes entirely (can't be seen or asserted), breaking the disabled contract."""
    xml = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.Button" resource-id="com.x:id/inc"
        text="+5" clickable="true" enabled="false"/>
</hierarchy>"""
    els = _elements(xml)
    inc = next((e for e in els if e.get("text") == "+5"), None)
    assert inc is not None, (
        "disabled short-numeric control dropped by the text filter — invisible to the LLM"
    )
    assert inc.get("clickable") is not True
    assert inc.get("disabled") is True


def test_missing_enabled_attr_defaults_to_clickable():
    # Most real nodes omit enabled (defaults true in Android). A clickable node
    # without an explicit enabled attr must NOT be treated as disabled.
    els = _elements()  # the original _XML has no enabled attrs
    row = next(e for e in els if e.get("text") == "显示与亮度")
    assert row.get("clickable") is True
    assert row.get("disabled") is not True
