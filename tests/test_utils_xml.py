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


# --- list-row label promotion (RecyclerView / Preference rows) ---------------
# The dominant Android list shape: a CLICKABLE container (LinearLayout / ViewGroup,
# no own text/desc) whose label lives in a NON-clickable child TextView. A flat
# walk splits one row into two elements — a headless clickable (unlocatable: no
# text/desc/id) and a text node marked clickable:false. Result: NO element is both
# clickable AND labeled, so neither workflow can target the row. Real-device proof
# (OPPO PEDM00 / Settings): 16 of 18 clickable elements were unlocatable, and
# d(text='应用') — self clickable=False — STILL navigated (tap bubbles to the
# clickable ancestor). Fix: promote the first label child to clickable:true (a real
# node with a real id) and suppress the now-redundant empty container. Zero coords.
# All fixtures below are faithful slices of the real PEDM00 Settings hierarchy.

_XML_ROW_SINGLE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.LinearLayout" clickable="true" enabled="true">
    <node class="android.widget.ImageView" resource-id="android:id/icon" clickable="false" enabled="true"/>
    <node class="android.widget.TextView" resource-id="android:id/title" text="应用" clickable="false" enabled="true"/>
    <node class="android.widget.ImageView" resource-id="com.android.settings:id/coui_jump" clickable="false" enabled="true"/>
  </node>
</hierarchy>"""

_XML_ROW_TITLE_SUB = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.LinearLayout" clickable="true">
    <node class="android.widget.ImageView" resource-id="android:id/icon" clickable="false"/>
    <node class="android.widget.TextView" resource-id="android:id/title" text="WLAN" clickable="false"/>
    <node class="android.widget.TextView" resource-id="com.android.settings:id/coui_statusText1" text="biying6-guest" clickable="false"/>
    <node class="android.widget.ImageView" resource-id="com.android.settings:id/coui_jump" clickable="false"/>
  </node>
</hierarchy>"""

# Outer clickable wrapper around a RecyclerView of two clickable cards, each with
# its own label. The inner cards must each promote their OWN first label; the outer
# wrapper has no label in its own scope (its texts live inside nested clickables) —
# it must NOT steal an inner label, and stays an honest headless clickable.
_XML_NESTED = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.RelativeLayout" clickable="true">
    <node class="androidx.recyclerview.widget.RecyclerView" resource-id="com.android.settings:id/message_entry_recycler_view" clickable="false">
      <node class="android.view.ViewGroup" resource-id="com.android.settings:id/message_entry_item" clickable="true">
        <node class="android.widget.ImageView" resource-id="com.android.settings:id/message_entry_icon" clickable="false"/>
        <node class="android.widget.TextView" resource-id="com.android.settings:id/message_entry_module" text="自由浮窗" clickable="false"/>
        <node class="android.widget.TextView" resource-id="com.android.settings:id/message_entry_title" text="通过视频快速上手浮窗功能" clickable="false"/>
      </node>
      <node class="android.view.ViewGroup" resource-id="com.android.settings:id/message_entry_item" clickable="true">
        <node class="android.widget.ImageView" resource-id="com.android.settings:id/message_entry_icon" clickable="false"/>
        <node class="android.widget.TextView" resource-id="com.android.settings:id/message_entry_module" text="单手模式" clickable="false"/>
        <node class="android.widget.TextView" resource-id="com.android.settings:id/message_entry_title" text="向下一滑，体验全新单手模式" clickable="false"/>
      </node>
    </node>
  </node>
</hierarchy>"""

_XML_ICON_ONLY = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" clickable="true">
    <node class="android.widget.ImageView" resource-id="com.x:id/avatar" clickable="false"/>
  </node>
</hierarchy>"""

_XML_ROW_DISABLED = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.LinearLayout" clickable="true" enabled="false">
    <node class="android.widget.TextView" resource-id="android:id/title" text="灰色项" clickable="false" enabled="false"/>
  </node>
</hierarchy>"""

_XML_STANDALONE_TEXT = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" clickable="false">
    <node class="android.widget.TextView" resource-id="com.x:id/note" text="纯文本说明" clickable="false"/>
  </node>
</hierarchy>"""


def _headless_clickables(els):
    """Clickable elements carrying no locator (no text/desc/id) — unlocatable."""
    return [
        e for e in els
        if e.get("clickable") and not e.get("text") and not e.get("desc") and not e.get("id")
    ]


def test_headless_clickable_row_promotes_child_label():
    els = _elements(_XML_ROW_SINGLE)
    app = next((e for e in els if e.get("text") == "应用"), None)
    assert app is not None, "row label disappeared"
    # The label child is promoted to clickable — a REAL node with a REAL id.
    assert app.get("clickable") is True, "row label not promoted to clickable — row is untargetable"
    assert app["id"] == "android:id/title"
    # The now-redundant empty container must be suppressed (no unlocatable clickable left).
    assert _headless_clickables(els) == [], "empty container not suppressed after promotion"


def test_title_subtitle_row_promotes_only_title():
    els = _elements(_XML_ROW_TITLE_SUB)
    wlan = next((e for e in els if e.get("text") == "WLAN"), None)
    sub = next((e for e in els if e.get("text") == "biying6-guest"), None)
    assert wlan is not None and wlan.get("clickable") is True, "title not promoted"
    # The subtitle stays emitted (assertable) but must NOT become a second tap target.
    assert sub is not None, "subtitle dropped"
    assert sub.get("clickable") is not True, "subtitle wrongly promoted to a click target"
    assert _headless_clickables(els) == []


def test_nested_clickable_cards_each_promote_own_label():
    els = _elements(_XML_NESTED)
    for label in ("自由浮窗", "单手模式"):
        e = next((x for x in els if x.get("text") == label), None)
        assert e is not None and e.get("clickable") is True, f"{label} not promoted to its own card"
    # Subtitles emitted but not clickable.
    for subtitle in ("通过视频快速上手浮窗功能", "向下一滑，体验全新单手模式"):
        e = next((x for x in els if x.get("text") == subtitle), None)
        assert e is not None and e.get("clickable") is not True, f"{subtitle} wrongly promoted"


def test_icon_only_clickable_stays_headless_honest():
    # No label to promote → keep the clickable container as-is. Unlocatable but
    # HONEST — never fabricate a label.
    els = _elements(_XML_ICON_ONLY)
    clickables = [e for e in els if e.get("clickable")]
    assert len(clickables) == 1, "icon-only clickable container should still surface"
    assert not clickables[0].get("text") and not clickables[0].get("desc"), (
        "icon-only container must not gain a fabricated label"
    )


def test_disabled_headless_row_does_not_promote_label():
    els = _elements(_XML_ROW_DISABLED)
    label = next((e for e in els if e.get("text") == "灰色项"), None)
    assert label is not None, "disabled row label dropped"
    # A disabled row is NOT effectively clickable — its label must not become a tap target.
    assert label.get("clickable") is not True, "disabled row label wrongly promoted to clickable"


def test_standalone_text_not_inside_clickable_stays_non_clickable():
    # Over-correction guard: a TextView with no clickable ancestor must stay non-clickable.
    els = _elements(_XML_STANDALONE_TEXT)
    t = next((e for e in els if e.get("text") == "纯文本说明"), None)
    assert t is not None and t.get("clickable") is not True, "standalone text wrongly made clickable"


# --- promotion must not drop a row whose label is itself filtered -------------
# Regression guard for a review finding: if the chosen label child carries a
# FILTERED id (com.android.systemui:id/...) or desc (VoLTE/OpenVPN), suppressing
# the container AND letting the emit-loop filter drop the label made the whole row
# VANISH — strictly worse than before (it used to survive as a headless clickable,
# still assertable). Promotion must be filter-aware: never suppress a container in
# favor of a label that won't survive emission.

_XML_ROW_FILTERED_ID_LABEL = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.LinearLayout" clickable="true">
    <node class="android.widget.ImageView" resource-id="android:id/icon" clickable="false"/>
    <node class="android.widget.TextView" resource-id="com.android.systemui:id/title" text="通知" clickable="false"/>
  </node>
</hierarchy>"""

_XML_ROW_FILTERED_DESC_LABEL = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.LinearLayout" clickable="true">
    <node class="android.widget.ImageView" resource-id="android:id/icon" clickable="false"/>
    <node class="android.widget.TextView" content-desc="VoLTE" clickable="false"/>
  </node>
</hierarchy>"""

# A clickable wrapper whose OWN content-desc is filtered (VoLTE) but which has a
# real, survivable child label. Treating the container as "already labeled" (by
# its filtered desc) would skip promotion AND then drop the container — row gone.
_XML_CONTAINER_FILTERED_OWN_DESC = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.LinearLayout" content-desc="VoLTE" clickable="true">
    <node class="android.widget.TextView" resource-id="android:id/title" text="语音通话" clickable="false"/>
  </node>
</hierarchy>"""


def test_row_with_filtered_id_label_survives_not_vanishes():
    # The label child has a filtered id; it cannot become the locator. The row must
    # NOT disappear — fall back to leaving the container as a headless clickable.
    els = _elements(_XML_ROW_FILTERED_ID_LABEL)
    assert els, "row vanished entirely — promotion dropped a filtered label AND its container"
    # The container must still be present and clickable (assertable / coordinate-free tap).
    assert any(e.get("clickable") for e in els), "row no longer surfaces a clickable element"


def test_row_with_filtered_desc_label_survives_not_vanishes():
    els = _elements(_XML_ROW_FILTERED_DESC_LABEL)
    assert els, "row vanished entirely — filtered-desc label dropped with its container"
    assert any(e.get("clickable") for e in els), "row no longer surfaces a clickable element"


def test_container_with_filtered_own_desc_promotes_real_child_label():
    # The wrapper's own desc is filtered, but its child '语音通话' is real → promote it.
    els = _elements(_XML_CONTAINER_FILTERED_OWN_DESC)
    label = next((e for e in els if e.get("text") == "语音通话"), None)
    assert label is not None and label.get("clickable") is True, (
        "real child label not promoted because the container's own (filtered) desc "
        "wrongly marked the row as already-labeled — row is untargetable"
    )
    assert _headless_clickables(els) == [], "redundant container not suppressed"


# --- promotion prefers the title over a summary that renders before it --------
# Review finding: promoting the *first label in document order* picks the wrong
# node when a status/summary line is laid out above the title. Prefer the
# `:id/title` node so the row's tap label is the title, not the status text.

_XML_ROW_SUMMARY_BEFORE_TITLE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.LinearLayout" clickable="true">
    <node class="android.widget.TextView" resource-id="com.android.settings:id/summary" text="已连接" clickable="false"/>
    <node class="android.widget.TextView" resource-id="android:id/title" text="蓝牙" clickable="false"/>
  </node>
</hierarchy>"""


def test_promotes_title_not_summary_when_summary_first():
    els = _elements(_XML_ROW_SUMMARY_BEFORE_TITLE)
    title = next((e for e in els if e.get("text") == "蓝牙"), None)
    summary = next((e for e in els if e.get("text") == "已连接"), None)
    assert title is not None and title.get("clickable") is True, (
        "title not promoted — summary line (rendered first) was wrongly chosen as the tap label"
    )
    assert summary is not None, "summary dropped"
    assert summary.get("clickable") is not True, "summary wrongly promoted to a click target"
