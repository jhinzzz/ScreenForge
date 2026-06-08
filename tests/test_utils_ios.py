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


# --- list-row label-shadow suppression (the iOS analog of the Android row fix) -
# Live-device finding (iPhone 16 Pro sim / iOS 18.3 / WDA, Settings): WDA nests a
# label-carrying StaticText INSIDE each row's interactive control, so a flat walk
# emits the SAME label 2-3x per row — a Button/Cell/Switch AND a redundant
# StaticText twin. Measured: 14 of 44 elements (32%) on the keyboard screen were
# pure StaticText shadows; ~half the rows on the Settings root. Cost: token bloat
# on every list screen + `d(label='通用')` is ambiguous (matches the tap target
# AND its inert text twin). All fixtures below are VERBATIM slices of the real
# PEDM-class hierarchy — never fabricated (iOS is exercised on a live simulator).
#
# The contract: within a row, keep ONE element per label — the highest-priority
# interactive control (Switch > Button > Cell) — and drop the same-label StaticText
# shadow. Honesty boundaries (also from live data): a StaticText whose label is
# DISTINCT from the row's control (a real subtitle, e.g. the account row) survives;
# a standalone StaticText with no interactive twin (e.g. '关'/Off) survives; a
# Switch keeps its on/off `value`.

# Root row: Cell(no own label) > Button('通用') > StaticText('通用'). The Button is
# the tap target (tap verified to navigate on device); the StaticText is a shadow.
_XML_ROW_BUTTON_SHADOW = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="设置" label="设置" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true" accessible="false">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="com.apple.settings.general" label="通用" enabled="true" visible="true" accessible="true">
      <XCUIElementTypeImage type="XCUIElementTypeImage" enabled="true" visible="true" accessible="false"/>
      <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="通用" label="通用" value="通用" enabled="true" visible="true" accessible="false"/>
      <XCUIElementTypeImage type="XCUIElementTypeImage" name="chevron.forward" enabled="true" visible="true" accessible="false"/>
    </XCUIElementTypeButton>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""

# Sub-screen row: Cell('关于本机') > StaticText('关于本机'). The Cell IS the labeled
# tap target (tap verified to navigate); the StaticText repeats its label.
_XML_ROW_CELL_SHADOW = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="通用" label="通用" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" name="关于本机" label="关于本机" enabled="true" visible="true" accessible="false">
    <XCUIElementTypeImage type="XCUIElementTypeImage" enabled="true" visible="true" accessible="false"/>
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="About" label="关于本机" value="关于本机" enabled="true" visible="true" accessible="true"/>
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="chevron" label="chevron" enabled="false" visible="true" accessible="false"/>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""

# Switch row: Cell('自动改正', value=0) > StaticText('自动改正') + Switch('自动改正', value=0).
# The Switch is the control that carries the on/off value; the StaticText is a shadow.
_XML_ROW_SWITCH_SHADOW = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="键盘" label="键盘" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" name="自动改正" label="自动改正" value="0" enabled="true" visible="true" accessible="true">
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="KeyboardAutocorrection" label="自动改正" value="自动改正" enabled="true" visible="true" accessible="true"/>
    <XCUIElementTypeSwitch type="XCUIElementTypeSwitch" name="自动改正" label="自动改正" value="0" enabled="true" visible="true" accessible="true"/>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""

# Account row: Button carries a COMBINED label; its StaticTexts have DISTINCT
# labels (a real title + subtitle). None is an exact shadow — all distinct labels
# must survive (the over-suppression guard).
_XML_ROW_DISTINCT_SUBTITLE = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="设置" label="设置" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true" accessible="false">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="com.apple.settings.primaryAppleAccount" label="Apple账户、登录以访问iCloud数据、App Store、Apple服务等。" enabled="true" visible="true" accessible="true">
      <XCUIElementTypeImage type="XCUIElementTypeImage" name="apple.id" label="apple.id" enabled="true" visible="true" accessible="false"/>
      <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="Apple账户" label="Apple账户" value="Apple账户" enabled="true" visible="true" accessible="false"/>
      <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="登录以访问iCloud数据、App Store、Apple服务等。" label="登录以访问iCloud数据、App Store、Apple服务等。" value="登录以访问iCloud数据、App Store、Apple服务等。" enabled="true" visible="true" accessible="false"/>
    </XCUIElementTypeButton>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""

# Standalone StaticText with NO interactive twin (a status caption '关'/Off).
_XML_STANDALONE_STATICTEXT = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="键盘" label="键盘" enabled="true" visible="true">
  <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="关" label="关" value="关" enabled="true" visible="true" accessible="true"/>
</XCUIElementTypeApplication>"""


def _labels(els):
    return [e.get("label") for e in els if e.get("label")]


def test_button_row_drops_staticext_shadow():
    els = _elements(_XML_ROW_BUTTON_SHADOW)
    same = [e for e in els if e.get("label") == "通用"]
    assert len(same) == 1, (
        f"label '通用' emitted {len(same)}x — the StaticText shadow of the Button "
        "was not suppressed (token bloat + ambiguous d(label='通用'))"
    )
    # The surviving element must be the actionable Button (a real tap target),
    # not the inert StaticText.
    assert same[0]["type"] == "Button", "kept the inert StaticText instead of the Button"
    assert same[0].get("name") == "com.apple.settings.general"


def test_cell_row_drops_staticext_shadow():
    els = _elements(_XML_ROW_CELL_SHADOW)
    same = [e for e in els if e.get("label") == "关于本机"]
    assert len(same) == 1, f"label '关于本机' emitted {len(same)}x — Cell+StaticText not deduped"
    # The Cell is the labeled, tappable row (tap verified to navigate on device).
    assert same[0]["type"] == "Cell"


def test_switch_row_keeps_switch_with_value_drops_shadow():
    els = _elements(_XML_ROW_SWITCH_SHADOW)
    same = [e for e in els if e.get("label") == "自动改正"]
    assert len(same) == 1, (
        f"label '自动改正' emitted {len(same)}x — Switch row not deduped to one element"
    )
    # The control that carries the on/off value must win over the StaticText shadow.
    assert same[0]["type"] == "Switch", "dropped the Switch — the toggle is no longer actionable"
    assert same[0].get("value") == "0", "Switch lost its on/off value during dedup"


def test_distinct_subtitle_survives_suppression():
    # Over-suppression guard: a row whose StaticTexts have labels DISTINCT from the
    # control's (a real title + subtitle) must keep them all.
    els = _elements(_XML_ROW_DISTINCT_SUBTITLE)
    labels = _labels(els)
    assert "Apple账户" in labels, "distinct title 'Apple账户' wrongly suppressed as a shadow"
    assert "登录以访问iCloud数据、App Store、Apple服务等。" in labels, (
        "distinct subtitle wrongly suppressed as a shadow"
    )
    # The Button (combined label) is still present and actionable.
    assert any(
        e.get("type") == "Button" and e.get("name") == "com.apple.settings.primaryAppleAccount"
        for e in els
    ), "account-row Button dropped"


def test_standalone_staticext_survives():
    # Honesty boundary: a caption with no interactive twin must NOT be dropped.
    els = _elements(_XML_STANDALONE_STATICTEXT)
    assert any(e.get("label") == "关" for e in els), (
        "standalone StaticText '关' (Off) wrongly suppressed — it has no interactive twin"
    )


# A row where the priority-WINNER (the Switch) is visible=false while its same-label
# siblings (Cell + StaticText) are visible=true. WDA marks subviews invisible
# routinely (partial scroll, occlusion, quirk flags), and visibility differs within
# one Cell. The shadow pass must NOT suppress the visible siblings in favor of an
# invisible winner that the emit loop then drops — that would make a real, on-screen
# row VANISH entirely (label + tap target + the Switch's on/off value all gone).
_XML_ROW_INVISIBLE_WINNER = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="键盘" label="键盘" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" name="自动改正" label="自动改正" value="0" enabled="true" visible="true" accessible="true">
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="KeyboardAutocorrection" label="自动改正" value="自动改正" enabled="true" visible="true" accessible="true"/>
    <XCUIElementTypeSwitch type="XCUIElementTypeSwitch" name="自动改正" label="自动改正" value="0" enabled="true" visible="false" accessible="true"/>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""


def test_invisible_winner_does_not_erase_visible_row():
    # Red-line #2/#5/#7: a visible on-screen row must never vanish because the
    # highest-priority element sharing its label happens to be invisible.
    els = _elements(_XML_ROW_INVISIBLE_WINNER)
    same = [e for e in els if e.get("label") == "自动改正"]
    assert same, (
        "the entire visible row vanished — the shadow pass suppressed the visible "
        "Cell/StaticText in favor of an invisible Switch the emit loop then dropped"
    )
    # Whatever survives must be a VISIBLE element (the emit loop only emits visible
    # nodes, so any survivor is visible by construction) and carry the on/off value
    # so the toggle state stays assertable.
    assert len(same) == 1, f"label '自动改正' emitted {len(same)}x — still duplicated"
    assert same[0].get("value") == "0", (
        "the surviving element lost the on/off value — toggle state no longer assertable"
    )


# Two DISTINCT rows that happen to share a label, nested (an outer Cell containing
# an inner Cell — grouped/inset table sections produce this). The inner row's only
# labelled element is a StaticText 'More'; the outer row has a Button 'More'. The
# shadow grouping must be scoped to DIRECT row membership: an outer Cell must not
# reach across a nested-Cell boundary and suppress the inner row's label, or the
# inner row loses its only locator and disappears from the brain's view.
_XML_NESTED_CELL_SHARED_LABEL = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="X" label="X" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="more.btn" label="More" enabled="true" visible="true" accessible="true"/>
    <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true">
      <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="inner" label="More" value="More" enabled="true" visible="true" accessible="true"/>
    </XCUIElementTypeCell>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""


def test_nested_cell_distinct_row_not_over_suppressed():
    # Red-line #2: the inner Cell is a separate row. Its 'More' StaticText must NOT
    # be suppressed by the outer row's 'More' Button — they belong to different rows.
    els = _elements(_XML_NESTED_CELL_SHARED_LABEL)
    labels = [e.get("label") for e in els]
    # Both rows' 'More' must survive: the outer Button AND the inner row's label.
    assert labels.count("More") == 2, (
        f"'More' emitted {labels.count('More')}x — the outer Cell reached across the "
        "nested-Cell boundary and ate the inner row's only label (inner row vanished)"
    )
    assert any(e.get("type") == "Button" and e.get("name") == "more.btn" for e in els)


# --- load-bearing-guard pins (constructed minimal cases, not device captures) ----
# The two cases below are not verbatim WDA slices; they are the smallest inputs that
# exercise two safety guards in _compute_label_shadows which had no dedicated test.
# Both guards already work (verified against the live code); these lock them so a
# future refactor that moved the visibility filter can't silently regress them.

# Boundary #8: a Cell whose only labelled members are StaticTexts (a caption/section
# row with NO interactive control) must be left wholly untouched — the `top < 1`
# guard. Two same-label StaticTexts with distinct names: neither the shadow pass
# (no interactive winner) nor the flat dedup_key (distinct names) may drop either.
_XML_ALL_STATICTEXT_ROW = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="X" label="X" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true">
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="a" label="仅文本" value="仅文本" enabled="true" visible="true" accessible="true"/>
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="b" label="仅文本" value="仅文本" enabled="true" visible="true" accessible="true"/>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""


def test_all_staticext_row_left_untouched():
    # `top < 1`: with no interactive control in the group, the row must NOT be
    # suppressed to nothing (red-line #8). The two distinct-name StaticTexts both
    # survive — the guard leaves an all-text group entirely alone.
    els = _elements(_XML_ALL_STATICTEXT_ROW)
    labels = [e.get("label") for e in els]
    assert "仅文本" in labels, "all-StaticText row erased — the `top < 1` guard failed"
    assert labels.count("仅文本") == 2, (
        f"'仅文本' emitted {labels.count('仅文本')}x — the shadow pass wrongly suppressed a "
        "member of an all-StaticText group (no interactive control = nothing to dedup to)"
    )


# Visibility-inverse of the invisible-winner case: the VISIBLE node is the
# low-priority StaticText and the higher-priority Button is invisible. visible_nodes
# has exactly ONE member, so the `len(visible_nodes) < 2` early-out must fire and
# leave the visible text alone. If suppression judged by ALL nodes (Button beats
# StaticText), the visible text would be dropped and the invisible Button too — the
# on-screen row would vanish.
_XML_VISIBLE_STATICTEXT_INVISIBLE_BUTTON = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="X" label="X" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true">
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="t" label="可见文本" value="可见文本" enabled="true" visible="true" accessible="true"/>
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="btn" label="可见文本" enabled="true" visible="false" accessible="true"/>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""


def test_visible_staticext_survives_invisible_higher_priority_twin():
    # `len(visible_nodes) < 2`: only the StaticText is visible, so there is nothing
    # to dedup — the visible on-screen text must survive even though an invisible
    # higher-priority Button shares its label (red-line #3, the inverse direction).
    els = _elements(_XML_VISIBLE_STATICTEXT_INVISIBLE_BUTTON)
    same = [e for e in els if e.get("label") == "可见文本"]
    assert same, (
        "visible StaticText vanished — suppression judged by all nodes and dropped the "
        "only on-screen element in favor of an invisible Button the emit loop also drops"
    )
    assert len(same) == 1 and same[0]["type"] == "StaticText", (
        "the surviving element must be the visible StaticText, not the invisible Button"
    )


# Issue 1 (documented, accepted): two SEPARATE rows whose interactive controls share
# an identical (type, label, name) AND each has a StaticText shadow. The shadow pass
# drops both StaticTexts; the flat dedup_key then collapses the two identical Buttons
# to one. So identically-named rows are not independently targetable. Benign for real
# WDA (each row's control has a unique name, e.g. com.apple.settings.general); only
# synthetic identical-name rows hit this, which d(label=...) could never disambiguate
# even before de-shadowing. This pins the accepted behavior the code comment cites.
_XML_DUPLICATE_NAME_ROWS = """<?xml version='1.0' encoding='UTF-8'?>
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="X" label="X" enabled="true" visible="true">
  <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="dup" label="重复" enabled="true" visible="true" accessible="true">
      <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="s1" label="重复" value="重复" enabled="true" visible="true" accessible="true"/>
    </XCUIElementTypeButton>
  </XCUIElementTypeCell>
  <XCUIElementTypeCell type="XCUIElementTypeCell" enabled="true" visible="true">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="dup" label="重复" enabled="true" visible="true" accessible="true">
      <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="s2" label="重复" value="重复" enabled="true" visible="true" accessible="true"/>
    </XCUIElementTypeButton>
  </XCUIElementTypeCell>
</XCUIElementTypeApplication>"""


def test_duplicate_name_rows_collapse_to_one_documented():
    # Documents the dedup_key × shadow-pass interaction (reviewer Issue 1): identical
    # (type, label, name) controls collapse to ONE element. This is accepted — the
    # flat dedup_key already collapsed them before de-shadowing, so the second row was
    # never distinctly targetable via its control. Asserting it keeps the behavior
    # visible: if it ever changes, this test forces a conscious decision.
    els = _elements(_XML_DUPLICATE_NAME_ROWS)
    same = [e for e in els if e.get("label") == "重复"]
    assert len(same) == 1, (
        f"'重复' emitted {len(same)}x — behavior changed from the documented single "
        "collapse; re-confirm the dedup_key interaction is still intended"
    )
    assert same[0]["type"] == "Button", "the surviving element must be the actionable Button"
