try:
    import defusedxml.ElementTree as ET
except ModuleNotFoundError:
    import xml.etree.ElementTree as ET
import json
import re

_PATTERN_NOISE = re.compile(r'^[\$\¥\€\£\d\.\,\+\-\%]+$')
_PATTERN_HASH_SUFFIX = re.compile(r'_[a-f0-9]{8}$')

def _should_filter_by_text(text: str, clickable: bool) -> bool:
    if clickable:
        return False
    if len(text) <= 5 and _PATTERN_NOISE.match(text):
        return True
    return False

def _should_filter_by_id(res_id: str) -> bool:
    if not res_id:
        return False
    return "com.android.systemui" in res_id

def _should_filter_by_desc(desc: str) -> bool:
    if not desc:
        return False
    if "OpenVPN" in desc or "VoLTE" in desc:
        return True
    if len(desc) > 30 and "0, 1, 2" in desc:
        return True
    return False

def _short_resource_id(res_id: str) -> str:
    """The bare id name (no package prefix), for display/token economy only.

    NOTE: do NOT use this as a locator value — uiautomator2's resourceId
    selector matches the FULL `pkg:id/name`, so the compressor emits the full id
    (see compress_android_xml). This helper exists only for the optional `id_short`
    hint.
    """
    short = res_id.split("/")[-1]
    short = _PATTERN_HASH_SUFFIX.sub('', short)
    return short

def compress_android_xml(raw_xml: str) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        raw_preview = raw_xml[:200] if raw_xml else "(empty)"
        print(f"[Warning] XML parse failed: {e}, first 200 chars: {raw_preview}")
        return '{"ui_elements": []}'

    elements = []

    for node in root.iter():
        attrib = node.attrib
        text = attrib.get("text", "").strip()
        desc = attrib.get("content-desc", "").strip()
        res_id = attrib.get("resource-id", "").strip()
        # `enabled` defaults to true in Android; only an explicit "false" disables.
        # A disabled control must not be reported clickable (the LLM would tap it
        # and hang on the timeout) but is still emitted so its existence/disabled
        # state stays assertable — mirrors the web compressor's disabled contract.
        disabled = attrib.get("enabled") == "false"
        clickable = attrib.get("clickable") == "true" and not disabled
        node_class = attrib.get("class", "").split(".")[-1]

        if _should_filter_by_id(res_id):
            continue

        if _should_filter_by_desc(desc):
            continue

        # Pass `clickable or disabled`: the numeric-noise filter must not drop a
        # disabled control (clickable is False for it), or its disabled state
        # could never be seen/asserted — the filter runs before emission.
        if _should_filter_by_text(text, clickable or disabled):
            continue

        if text or desc or clickable or disabled:
            el_info = {"class": node_class}
            if text: el_info["text"] = text
            if desc: el_info["desc"] = desc
            if clickable: el_info["clickable"] = True
            if disabled: el_info["disabled"] = True

            if res_id:
                # Emit the FULL resource-id (pkg:id/name) — this is what
                # uiautomator2's resourceId selector matches. Stripping the
                # prefix produced ids that could never be located (the agent's
                # #2-priority locator was silently broken on Android).
                el_info["id"] = res_id
                short = _short_resource_id(res_id)
                if short and short != res_id:
                    el_info["id_short"] = short

            elements.append(el_info)

    return json.dumps({"ui_elements": elements}, ensure_ascii=False)
