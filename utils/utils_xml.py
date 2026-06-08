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

def _node_label(node) -> str:
    """A node's own label (text, falling back to content-desc), stripped."""
    return node.attrib.get("text", "").strip() or node.attrib.get("content-desc", "").strip()


def _is_filtered_node(node) -> bool:
    """True if the emit loop will drop this node entirely (id / desc filters).

    A clickable/promoted node survives the numeric-noise *text* filter, so only
    `_should_filter_by_id` / `_should_filter_by_desc` matter — they `continue`
    past the node regardless of its label. Promotion must consult this so it
    never suppresses a row container in favor of a label that then vanishes.
    """
    res_id = node.attrib.get("resource-id", "").strip()
    desc = node.attrib.get("content-desc", "").strip()
    return _should_filter_by_id(res_id) or _should_filter_by_desc(desc)


def _emittable_own_label(node) -> bool:
    """The node carries its own label AND will survive emission — i.e. it is
    already a locatable control (a Button, a labeled clickable), not a headless
    container needing promotion. A container whose only own label is itself
    filtered (e.g. a clickable wrapper with content-desc='VoLTE') is treated as
    label-less so its real child label can still be promoted."""
    return bool(_node_label(node)) and not _is_filtered_node(node)


def _scope_label_descendants(container) -> list:
    """Surviving labeled descendants in document order, without crossing a nested
    clickable boundary (an inner card owns its own labels). Labels the emit loop
    would drop (filtered id/desc) are skipped, so promotion never targets — nor
    suppresses a container in favor of — a node that would vanish."""
    out: list = []
    for child in container:
        if child.attrib.get("clickable") == "true":
            continue  # nested clickable owns its own subtree's labels
        if _node_label(child) and not _is_filtered_node(child):
            out.append(child)
        out.extend(_scope_label_descendants(child))
    return out


def _promotable_label(container):
    """The label node to promote for a headless clickable container, or None.

    Prefers the standard `:id/title` node when present, else the first surviving
    label in document order — so a summary/status line that happens to render
    before the title (e.g. '已连接' above '蓝牙') doesn't become the row's tap
    label. Returns None for an icon-only container or one whose only labels are
    all filtered (→ left as an honest headless clickable, never fabricated)."""
    labels = _scope_label_descendants(container)
    if not labels:
        return None
    for node in labels:
        if node.attrib.get("resource-id", "").strip().endswith("/title"):
            return node
    return labels[0]


def _compute_row_promotions(root):
    """Find list-row label promotions (RecyclerView / Preference rows).

    The dominant Android list shape is a CLICKABLE container with no own label
    whose text lives in a non-clickable child TextView. A flat walk splits the
    row into a headless (unlocatable) clickable + a text node marked not-clickable,
    so NO element is both clickable and labeled. We promote the container's title
    (or first surviving) label descendant to clickable (a real node with a real id
    — tapping it bubbles to the clickable ancestor, verified on a real device) and
    suppress the now-redundant empty container.

    Returns (promote_ids, suppress_ids): sets of id(node) for Pass 2 to apply.
    Identity keys are safe because `root` (and all its Element nodes) is held
    alive across both passes within compress_android_xml; do not stream/re-parse
    between the passes.

    Honesty boundaries:
      - Disabled container (enabled=false) → not effectively clickable, no promotion.
      - No promotable, *survivable* label (icon-only, or only filtered labels) →
        container left as an honest headless clickable; never fabricate a label and
        never suppress a row in favor of a label that the emit loop would drop.
      - Label search does NOT cross into a nested clickable — an inner card's label
        belongs to the inner card, so an outer wrapper can't steal it (an outer
        wrapper around already-promoted inner cards stays an honest, locator-less
        clickable rather than being given a borrowed label).
    """
    promote_ids: set[int] = set()
    suppress_ids: set[int] = set()

    for node in root.iter():
        if node.attrib.get("clickable") != "true":
            continue
        if node.attrib.get("enabled") == "false":
            continue  # disabled row is not effectively clickable — don't promote
        if _emittable_own_label(node):
            continue  # already a locatable control (e.g. a Button) — nothing to lift

        label_node = _promotable_label(node)
        if label_node is None:
            # Icon-only container, or every candidate label would be filtered out:
            # leave the container un-suppressed (today's headless-clickable, still
            # present/assertable) rather than dropping the row entirely.
            continue

        promote_ids.add(id(label_node))
        suppress_ids.add(id(node))

    # Never suppress a node we also promote (defensive; can't currently coincide).
    suppress_ids -= promote_ids
    return promote_ids, suppress_ids


def compress_android_xml(raw_xml: str) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        raw_preview = raw_xml[:200] if raw_xml else "(empty)"
        print(f"[Warning] XML parse failed: {e}, first 200 chars: {raw_preview}")
        return '{"ui_elements": []}'

    elements = []
    promote_ids, suppress_ids = _compute_row_promotions(root)

    for node in root.iter():
        if id(node) in suppress_ids:
            # Redundant empty row container — its label child carries the row now.
            continue

        attrib = node.attrib
        text = attrib.get("text", "").strip()
        desc = attrib.get("content-desc", "").strip()
        res_id = attrib.get("resource-id", "").strip()
        # `enabled` defaults to true in Android; only an explicit "false" disables.
        # A disabled control must not be reported clickable (the LLM would tap it
        # and hang on the timeout) but is still emitted so its existence/disabled
        # state stays assertable — mirrors the web compressor's disabled contract.
        disabled = attrib.get("enabled") == "false"
        # A row label promoted from a headless clickable container is effectively
        # clickable (tap bubbles to the clickable ancestor — real-device verified);
        # a disabled node is never promoted (excluded in _compute_row_promotions).
        promoted = id(node) in promote_ids
        clickable = (attrib.get("clickable") == "true" or promoted) and not disabled
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
