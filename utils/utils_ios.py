"""iOS WDA XML compression and dimensionality reduction."""

import json
import xml.etree.ElementTree as ET

_SKIP_TYPES = frozenset(("Window", "Application"))
_KEYBOARD_TYPES = frozenset(("Key",))
_NOISE_LABEL_MAX_LEN = 1

# How strongly a node type represents "the actionable control" of a row. WDA
# repeats a row's label on a nested StaticText AND on the control that carries it
# (a Switch/Button, or the Cell itself); the StaticText is an inert shadow. When
# several elements in one row share an exact label, the highest-priority type wins
# and strictly-lower ones are suppressed — collapsing the inert StaticText shadow
# while keeping the actionable control. (Equal-priority ties — e.g. two same-label
# Buttons in one row — are both kept; that's two real controls, not a shadow.)
_INTERACTIVE_PRIORITY = {"Switch": 3, "Button": 2, "Cell": 1}


def _ios_type(node) -> str:
    """Element type without the verbose XCUIElementType prefix."""
    return node.attrib.get("type", "").replace("XCUIElementType", "")


def _interactive_priority(node_type: str) -> int:
    """Higher = more 'the actionable control'. A label-shadow StaticText is 0 and
    loses to the Switch/Button/Cell carrying the same label."""
    return _INTERACTIVE_PRIORITY.get(node_type, 0)


def _row_members(cell):
    """The Cell plus its descendants that belong to THIS row — stopping the descent
    at any nested Cell (a separate row owns its own labels). Without this boundary,
    an outer Cell's label group would swallow an inner row's distinct label and
    suppress it, erasing the inner row from the output."""
    yield cell
    for child in cell:
        if _ios_type(child) == "Cell":
            continue  # nested row — its labels belong to it, not to `cell`
        yield from _row_members(child)


def _compute_label_shadows(root) -> set:
    """Find redundant label-shadow nodes to suppress (returns a set of id(node)).

    WDA models every Settings/list row as a `Cell`, and repeats the row's label on
    a nested `StaticText` AND on the row's interactive control. A flat walk emits
    the same label 2-3x — a Button/Cell/Switch plus a StaticText twin (a Switch row
    yields Cell + StaticText + Switch, all labelled the same). That bloats the tree
    and makes `d(label=...)` ambiguous (it matches the tap target AND its inert text
    twin). Within each row we group labelled members (the Cell + its non-nested-Cell
    descendants) by EXACT label and suppress every element whose interactive priority
    is strictly below the group's max — keeping the actionable control per label and
    dropping the inert StaticText shadow. Equal-priority ties are preserved (two real
    same-label controls are not a shadow).

    Identity keys are safe because `root` is held alive across both passes inside
    compress_ios_xml; do not stream/re-parse between the passes.

    Honesty boundaries (verified on a live simulator):
      - EXACT-label match only. A real subtitle whose text merely contains the
        control's label (e.g. the Apple-account row, whose Button carries a combined
        label and whose StaticTexts are distinct title/subtitle) is NOT a shadow and
        survives.
      - Scope is the row (a Cell, NOT descending into a nested Cell — see
        _row_members). A StaticText with no Cell ancestor (a standalone caption like
        '关'/Off) is never grouped, so it survives; and an inner row's distinct label
        is never eaten by the outer row that contains it.
      - A label-group with no interactive element (all StaticText) is left untouched —
        never suppress a row down to nothing; the row's tap target is preserved.
      - VISIBILITY-AWARE. Pass 2 emits only visible nodes, so the priority winner is
        chosen among VISIBLE nodes and only VISIBLE nodes are suppressed. Otherwise an
        invisible higher-priority twin (WDA marks subviews invisible routinely) would
        suppress the visible sibling and then be dropped itself — erasing a real,
        on-screen row entirely (label + tap target + any value). Suppressing only
        visible nodes is sufficient: invisible ones never reach the output anyway.
    """
    suppress: set = set()
    for cell in root.iter():
        if _ios_type(cell) != "Cell":
            continue
        groups: dict = {}
        for node in _row_members(cell):  # this row only — not nested-Cell rows
            label = node.attrib.get("label", "").strip()
            if label:
                groups.setdefault(label, []).append(node)
        for nodes in groups.values():
            # Only nodes the emit loop will actually keep (visible) can be a shadow
            # or a winner — judging by all nodes lets an invisible winner erase a
            # visible row (the winner is then dropped by Pass 2's visibility filter).
            visible_nodes = [n for n in nodes if n.attrib.get("visible") == "true"]
            if len(visible_nodes) < 2:
                continue  # 0/1 visible element with this label — nothing to dedup
            top = max(_interactive_priority(_ios_type(n)) for n in visible_nodes)
            if top < 1:
                continue  # no visible interactive element — keep them all
            for node in visible_nodes:
                if _interactive_priority(_ios_type(node)) < top:
                    suppress.add(id(node))
    return suppress


def compress_ios_xml(raw_xml: str) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        raw_preview = raw_xml[:200] if raw_xml else "(empty)"
        print(f"[Warning] iOS XML parse failed: {e}, first 200 chars: {raw_preview}")
        return '{"ui_elements": []}'

    elements = []
    seen_keys = set()
    has_keyboard = False
    # Pass 1: within each row (Cell), find label-shadow StaticTexts that merely
    # repeat the row control's label, so Pass 2 emits ONE targetable element per
    # row instead of a Button/Cell/Switch + its inert text twin. `root` stays alive
    # across both passes (id()-keyed), so don't re-parse between them.
    shadow_ids = _compute_label_shadows(root)

    for node in root.iter():
        if id(node) in shadow_ids:
            continue  # redundant label-shadow — the row's actionable control carries it.

        attrib = node.attrib
        label = attrib.get("label", "").strip()
        name = attrib.get("name", "").strip()
        value = attrib.get("value", "").strip()
        node_type = attrib.get("type", "").replace("XCUIElementType", "")
        enabled = attrib.get("enabled") == "true"
        visible = attrib.get("visible") == "true"
        accessible = attrib.get("accessible") == "true"

        if not visible:
            continue

        if not (label or name or value or accessible):
            continue

        if node_type in _SKIP_TYPES:
            if not label:
                continue

        if node_type == "Other" and not label:
            continue

        if node_type in _KEYBOARD_TYPES:
            has_keyboard = True
            continue

        if node_type == "WebView" and not label:
            continue

        if label and ("滚动条" in label or "scroll bar" in label.lower()):
            continue

        if node_type == "StaticText" and label and len(label) <= _NOISE_LABEL_MAX_LEN:
            if label.isdigit() or label in (".", ","):
                continue

        # Flat exact-dedup (pre-existing): collapse repeated (type, label, name),
        # except Cells (each Cell is its own row). Note its interaction with the
        # shadow pass above: two SEPARATE rows whose interactive controls share an
        # identical (type, label, name) collapse to a single element here, and their
        # StaticText shadows were already suppressed — so identically-named rows are
        # not independently targetable. Benign for real WDA, where each row's control
        # carries a unique name (e.g. com.apple.settings.general); it only affects
        # synthetic identical-name rows, which d(label=...) could not disambiguate
        # even before de-shadowing. Pinned by test_duplicate_name_rows_* in
        # tests/test_utils_ios.py.
        dedup_key = (node_type, label, name)
        if dedup_key in seen_keys and node_type != "Cell":
            continue
        seen_keys.add(dedup_key)

        el_info = {"type": node_type}
        if label:
            el_info["label"] = label
        if name and name != label:
            el_info["name"] = name
        if value:
            el_info["value"] = value
        if accessible:
            el_info["accessible"] = True
        # Unified cross-platform key: a disabled control is `disabled: true`,
        # matching Android (utils_xml.py) and Web (utils_web.py), so the LLM brain
        # sees one vocabulary for "can't interact" on every platform.
        if not enabled:
            el_info["disabled"] = True

        elements.append(el_info)

    if has_keyboard:
        elements.append({"type": "Keyboard", "label": "keyboard_visible"})

    return json.dumps({"ui_elements": elements}, ensure_ascii=False)
