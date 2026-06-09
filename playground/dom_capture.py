"""Sidecar HIERARCHICAL tree capture for the Playground "Brain's Eye View".

These builders produce a parent/child tree of the AI brain's FILTERED element
set — only surviving (interactive / labeled / assertable) nodes, re-hung under
their nearest surviving ancestor (dead layout wrappers collapse out). This is
PLAYGROUND-ONLY: it reuses the compressors' survival predicates but NEVER touches
utils_web.py / utils_xml.py (the sacred LLM-facing path) and is captured on the
opt-in --playground-sink observer path. Any failure returns None (degrade, never
crash the action being observed).
"""

import xml.etree.ElementTree as ET

# Reuse the EXACT survival/filter predicates the flat Android compressor uses,
# so the tree shows precisely what the brain would have seen — never modify them.
from utils.utils_xml import (
    _compute_row_promotions,
    _short_resource_id,
    _should_filter_by_desc,
    _should_filter_by_id,
    _should_filter_by_text,
)


def _mobile_node_dict(node, promote_ids, suppress_ids):
    """Build a single node's dict (no children) mirroring compress_android_xml's
    emit logic, or return None if this node is filtered/suppressed/non-surviving."""
    if id(node) in suppress_ids:
        return None
    attrib = node.attrib
    text = attrib.get("text", "").strip()
    desc = attrib.get("content-desc", "").strip()
    res_id = attrib.get("resource-id", "").strip()
    disabled = attrib.get("enabled") == "false"
    promoted = id(node) in promote_ids
    clickable = (attrib.get("clickable") == "true" or promoted) and not disabled
    node_class = attrib.get("class", "").split(".")[-1]

    if _should_filter_by_id(res_id):
        return None
    if _should_filter_by_desc(desc):
        return None
    if _should_filter_by_text(text, clickable or disabled):
        return None
    if not (text or desc or clickable or disabled):
        return None

    out = {"class": node_class}
    if text:
        out["text"] = text
    if desc:
        out["desc"] = desc
    if clickable:
        out["clickable"] = True
    if disabled:
        out["disabled"] = True
    if res_id:
        out["id"] = res_id
        short = _short_resource_id(res_id)
        if short and short != res_id:
            out["id_short"] = short
    return out


def _build_mobile_forest(el, promote_ids, suppress_ids):
    """Return the list of surviving tree-nodes for el's subtree.

    If el survives → [ {..el.., children: <forest of its descendants>} ].
    If el is filtered → its descendants' forest is lifted to el's parent level
    (dead wrapper collapses out).
    """
    children_forest = []
    for child in el:
        children_forest.extend(_build_mobile_forest(child, promote_ids, suppress_ids))
    self_dict = _mobile_node_dict(el, promote_ids, suppress_ids)
    if self_dict is None:
        return children_forest  # collapse: lift children
    self_dict["children"] = children_forest
    return [self_dict]


def build_mobile_tree(raw_xml, platform):
    """Parse raw Android XML into a hierarchical filtered tree, or None.

    HONEST v1 BOUNDARY: these predicates are the ANDROID ones (text/content-desc/
    resource-id/clickable/enabled). iOS WDA `.source()` returns XCUITest XML with
    different attributes (XCUIElementType* tags + name/label/value/type), so every
    iOS node is filtered out → empty forest → None (no tree, pip stays dark). iOS
    DOM-tree capture is therefore NOT yet supported; WDA-predicate support is a
    future addition. Never crashes either way (empty → None, parse error → None).
    """
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return None
    try:
        promote_ids, suppress_ids = _compute_row_promotions(root)
        forest = []
        for child in root:
            forest.extend(_build_mobile_forest(child, promote_ids, suppress_ids))
        # The root <hierarchy> itself is a non-surviving wrapper; if a builder ever
        # passes a surviving root, include it too:
        root_self = _mobile_node_dict(root, promote_ids, suppress_ids)
        if root_self is not None:
            root_self["children"] = forest
            forest = [root_self]
        if not forest:
            return None  # no surviving elements ⇒ no tree to show (keeps has_dom_tree truthful:
                         # iOS XCUITest XML yields nothing under the Android predicates, and a
                         # genuinely empty page has nothing to render — both should leave the pip dark)
        return {"platform": platform, "nodes": forest}
    except Exception:
        return None


def build_web_tree(page):
    """Inject a hierarchical-DOM JS into the live Playwright page; return tree|None.

    Mirrors how compress_web_dom(adapter.driver) calls page.evaluate, but emits a
    NESTED structure instead of a flat list. Any failure → None (degrade).
    """
    try:
        result = page.evaluate(_WEB_TREE_JS)
        if not isinstance(result, dict) or "nodes" not in result:
            return None
        if not result["nodes"]:
            return None  # blank page / nothing survived ⇒ no tree (keeps has_dom_tree truthful)
        result["platform"] = "web"
        return result
    except Exception:
        return None


# Injected once per capture. Walks document.documentElement applying the same
# survival predicates compress_web_dom uses, but builds a TREE: a surviving node
# nests under its nearest surviving ancestor; dead wrappers collapse (children
# lift). open shadow DOM + same-origin iframes are traversed (coordinates offset
# to top-level). Cross-origin frames / closed shadow roots are skipped silently.
_WEB_TREE_JS = r"""
() => {
  const interactiveRoles = new Set(['button','link','checkbox','radio','switch',
    'tab','menuitem','option','textbox','combobox','slider','searchbox']);
  let refIndex = 0;

  function isInertEl(el, inherited) {
    if (inherited) return true;
    try { return el.closest && el.closest('[inert]') !== null; } catch (e) { return false; }
  }

  function nodeOf(el, offX, offY, inheritedInert) {
    const tag = el.tagName ? el.tagName.toLowerCase() : '';
    let rect; try { rect = el.getBoundingClientRect(); } catch (e) { return null; }
    const style = (el.ownerDocument.defaultView || window).getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return null;

    const role = el.getAttribute('role');
    const isInteractive = ['a','button','input','select','textarea'].includes(tag)
      || el.hasAttribute('onclick') || interactiveRoles.has(role);
    const isSemantic = isInteractive;
    const directText = (el.childNodes ? Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim() : '');
    const fullText = (el.innerText || '').trim();
    const ariaLabel = el.getAttribute('aria-label') || el.getAttribute('title')
      || el.getAttribute('alt') || '';
    const keep = isInteractive || isSemantic;
    if (!keep && !directText && !ariaLabel) return null;

    const displayText = keep ? (fullText || directText)
      : (directText.length > 0 ? fullText : directText);
    const placeholder = el.getAttribute('placeholder') || '';
    const type = el.getAttribute('type') || '';
    const name = el.getAttribute('name') || '';
    if (!displayText && !ariaLabel && !placeholder
        && !['input','select','textarea'].includes(tag)) return null;

    let disabled = false;
    try { disabled = el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true'; }
    catch (e) { disabled = false; }
    const inert = isInertEl(el, inheritedInert);

    refIndex++;
    const node = { ref: '@' + refIndex, class: tag, clickable: isInteractive && !disabled };
    if (el.id) node.id = el.id;
    if (name) node.name = name;
    if (type) node.type = type;
    if (placeholder) node.placeholder = placeholder;
    if (ariaLabel) node.desc = ariaLabel;
    if (displayText) node.text = displayText.slice(0, 120);
    if (disabled) node.disabled = true;
    if (inert) node.inert = true;
    node.x = Math.round(rect.x + offX);
    node.y = Math.round(rect.y + offY);
    node.w = Math.round(rect.width);
    node.h = Math.round(rect.height);
    node.children = [];
    return node;
  }

  // Returns the forest of surviving nodes for `root`'s children.
  function walkForest(root, offX, offY, depth, inheritedInert) {
    if (depth > 50) return [];
    let kids; try { kids = Array.from(root.children || []); } catch (e) { return []; }
    const forest = [];
    for (const el of kids) {
      const tag = el.tagName ? el.tagName.toLowerCase() : '';
      if (tag === 'iframe') {
        const frameInert = inheritedInert || isInertEl(el, false);
        try {
          const fr = el.getBoundingClientRect();
          const cs = (el.ownerDocument.defaultView || window).getComputedStyle(el);
          const ix = (parseFloat(cs.borderLeftWidth)||0) + (parseFloat(cs.paddingLeft)||0);
          const iy = (parseFloat(cs.borderTopWidth)||0) + (parseFloat(cs.paddingTop)||0);
          const doc = el.contentDocument;
          if (doc && doc.documentElement) {
            const inner = walkForest(doc.documentElement, offX+fr.x+ix, offY+fr.y+iy, depth+1, frameInert);
            forest.push(...inner);
          }
        } catch (e) { /* cross-origin: skip silently */ }
        continue;
      }
      const self = nodeOf(el, offX, offY, inheritedInert);
      const childInert = self ? !!self.inert : inheritedInert;
      let descendants = walkForest(el, offX, offY, depth+1, childInert);
      if (el.shadowRoot) {
        try { descendants = descendants.concat(
          walkForest(el.shadowRoot, offX, offY, depth+1, childInert)); } catch (e) {}
      }
      if (self) { self.children = descendants; forest.push(self); }
      else { forest.push(...descendants); }  // collapse dead wrapper
    }
    return forest;
  }

  const nodes = walkForest(document.documentElement, 0, 0, 0, false);
  return { nodes };
}
"""
