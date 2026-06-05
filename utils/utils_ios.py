"""iOS WDA XML compression and dimensionality reduction."""

import json
import xml.etree.ElementTree as ET

_SKIP_TYPES = frozenset(("Window", "Application"))
_KEYBOARD_TYPES = frozenset(("Key",))
_NOISE_LABEL_MAX_LEN = 1


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

    for node in root.iter():
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
