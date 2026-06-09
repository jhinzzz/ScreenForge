# Playground "Brain's Eye View" DOM Tree Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, live, hierarchical DOM-tree panel ("Brain's Eye View") to the Playground that shows the AI brain's filtered element set re-hung into its real parent/child structure, updating per step, with the current target element ember-lit and (on web) cross-linked to a bbox overlay on the screenshot.

**Architecture:** A **sidecar** hierarchical tree is captured on the existing `--playground-sink` observer path — a NEW module `playground/dom_capture.py` that reuses the compressors' survival predicates but preserves hierarchy, **without touching the LLM-facing `compress_web_dom` / `compress_android_xml`**. Trees are pushed via a **separate fire-and-forget `POST /api/dom`** (decoupled from the lean step/screenshot push so they never delay it). The **resident server owns the tree store on disk, keyed by `run_key`** (the cross-process-stable playground key), because in session mode N `--action` processes share one `run_key` but each has its own reporter dir — the producer cannot own the path. SSE carries only a `has_dom_tree` boolean; the frontend fetches trees **on demand** via `GET /api/run/{run_id}/step/{step_index}/dom`. Frontend is a vanilla-JS keyed reconciler + renderer + bbox overlay + ARIA keyboard nav + search + copy-locator, all inside the single-file `playground/index.html` on the existing forge/ember tokens.

**Tech Stack:** Python 3.11, FastAPI (playground extra), `xml.etree.ElementTree` (stdlib), Playwright `page.evaluate`, pytest + FastAPI `TestClient`, vanilla JS + Prism.js (zero-build single-file HTML). No new dependencies.

---

## Conventions & Guardrails (read once before starting)

- **Loguru only** (never `print`/stdlib `logging`) in `cli/`; `playground/dom_capture.py` is degrade-silent (`return None` on any exception — no logging needed in the hot path, mirror `encode_screenshot`).
- **Red line (exit-code contract):** the sink/observer path must NEVER change `--action`'s `0/1` exit code or block it. Tree capture is gated by `--playground-sink` (off by default = zero cost). The tree POST is fire-and-forget with **no join** (unlike the step push which keeps its `_JOIN_TIMEOUT`).
- **Do NOT modify** `utils/utils_web.py` or `utils/utils_xml.py` or `utils/utils_ios.py`. Import their predicate helpers; never edit them.
- **No `Co-Authored-By` Claude trailer** in any commit (repo rule).
- **`git checkout -- AGENTS.md`** before committing if it shows as changed.
- **CI reproduction before any push** (3 steps, real exit codes — zsh: check `$?` per command, not `${PIPESTATUS}`):
  1. `ruff check .` (whole repo — `dom_capture.py` must pass E,F,W,I)
  2. `mypy cli/ common/ config/ utils/` (note: `playground/` is OUT of mypy scope; `cli/playground_sink.py` is IN, leniently)
  3. `pytest tests/ -q`
- **Frontend TDD adaptation:** this repo has **no JS test harness** (the 2159-line `index.html` has zero JS unit tests by design — it uses the offline demo feed `USE_LIVE_BACKEND=false` as its verification harness). Do NOT introduce a JS test framework (violates "follow existing patterns"). Frontend tasks verify via: (a) Python contract tests already pinning the data shape, (b) the offline demo feed extended with a fake tree, (c) a documented manual browser checklist. This is the honest TDD path for a zero-build single-file frontend.
- **Commit cadence:** one commit per task (after its verification passes).

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `playground/dom_capture.py` | **Create** | Sidecar hierarchical tree builders: `build_mobile_tree(raw_xml, platform)` (pure, stdlib ET, reuses `utils_xml` predicates) + `build_web_tree(page)` (Playwright `evaluate` of a NEW hierarchical JS). Stdlib + passed-in objects only; no fastapi import (always import-safe). |
| `cli/playground_sink.py` | Modify | Add `PlaygroundSink.capture_dom_tree(adapter, platform)` static (lazy-imports `dom_capture`, G5 try/except → None); add `has_dom_tree` to `PlaygroundStepEvent` + `build_step_event`; in `maybe_push_step`, capture tree, set the bool, and after the step push do a separate fire-and-forget `POST /api/dom`. |
| `playground/app.py` | Modify | Disk-backed, `run_key`-keyed tree store (LRU ≤5 run dirs); `POST /api/dom`; `GET /api/run/{run_id}/step/{step_index}/dom` (404 if absent); confirm `has_dom_tree` flows through the existing `post_step` SSE passthrough. |
| `playground/index.html` | Modify | CSS (drawer, tree rows, flag chips, bbox overlay, animations — forge tokens, ~150 LOC) + HTML (drawer, toggle tab, diff badge, search, overlay div) + JS (drawer state, on-demand fetch, renderer, keyed reconciler, bbox overlay, ARIA keyboard nav, search, copy-locator, wiring into `onStepEvent`/`selectStep`/`resetTimeline`, mobile degrade — ~400 LOC). |
| `tests/test_dom_capture.py` | **Create** | TDD for `build_mobile_tree` (XML fixtures: hierarchy, filter reuse, scope/dup, None-on-error) + `build_web_tree` wrapper (mock page passthrough + None-on-raise). |
| `tests/test_playground_app.py` | Modify | Extend: `POST /api/dom` persists; `GET .../dom` returns stored / 404 absent; LRU dir eviction; `has_dom_tree` SSE passthrough. |
| `tests/test_playground_sink.py` | Modify | Extend: `capture_dom_tree` disabled=no-op; tree POST fire-and-forget + swallowed errors; `has_dom_tree` set correctly. |

**Data contract (both builders emit this exact shape):**
```json
{
  "platform": "web|android|ios",
  "nodes": [
    {
      "ref": "@1",            // web only; absent on mobile
      "class": "button",
      "text": "Log in",        // optional
      "desc": "",              // optional (aria-label / content-desc)
      "id": "submit",          // optional
      "clickable": true,        // optional (omit when false)
      "disabled": true,         // optional (omit when false)
      "inert": true,            // optional (omit when false)
      "scope": "Bob Jones",    // optional (disambiguation row context)
      "dup_index": 2,           // optional
      "x": 10, "y": 20, "w": 80, "h": 30,  // web only; absent on mobile
      "children": [ ...same shape... ]
    }
  ]
}
```

---

## Phase 1 — Sidecar capture (Python, fully TDD)

### Task 1: Mobile hierarchical tree builder (`build_mobile_tree`)

**Files:**
- Create: `playground/dom_capture.py`
- Test: `tests/test_dom_capture.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dom_capture.py`:

```python
"""Tests for playground/dom_capture.py — the sidecar HIERARCHICAL tree builders.

Unlike utils/utils_xml.py (which flattens for the LLM), these preserve parent/
child so the playground can render a real tree. They REUSE utils_xml predicates
(never modify them) and degrade to None on any failure (never crash the sink).
"""

import pytest

from playground.dom_capture import build_mobile_tree, build_web_tree


class TestBuildMobileTree:
    def test_returns_none_on_parse_error(self):
        assert build_mobile_tree("<<not xml", "android") is None

    def test_empty_hierarchy_yields_empty_nodes(self):
        xml = '<hierarchy rotation="0"></hierarchy>'
        tree = build_mobile_tree(xml, "android")
        assert tree == {"platform": "android", "nodes": []}

    def test_single_clickable_node_emitted(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="Login" clickable="true"/>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert tree["platform"] == "android"
        assert len(tree["nodes"]) == 1
        n = tree["nodes"][0]
        assert n["class"] == "Button"
        assert n["text"] == "Login"
        assert n["clickable"] is True
        assert n["children"] == []

    def test_hierarchy_is_preserved_not_flattened(self):
        # A clickable container with a labeled child: the tree keeps the nesting
        # (the FLAT compressor would emit them as siblings; we must not).
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.LinearLayout" text="Settings" clickable="true">'
            '  <node class="android.widget.TextView" text="Wi-Fi"/>'
            '</node>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert len(tree["nodes"]) == 1
        parent = tree["nodes"][0]
        assert parent["text"] == "Settings"
        assert len(parent["children"]) == 1
        assert parent["children"][0]["text"] == "Wi-Fi"

    def test_dead_wrapper_collapses_lifting_children(self):
        # A non-surviving wrapper (no text/desc/clickable/disabled) must NOT appear;
        # its surviving child lifts to the wrapper's parent level.
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.FrameLayout">'
            '  <node class="android.widget.Button" text="OK" clickable="true"/>'
            '</node>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert len(tree["nodes"]) == 1
        assert tree["nodes"][0]["text"] == "OK"   # lifted, wrapper gone

    def test_disabled_emitted_without_clickable(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="Send" enabled="false"/>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        n = tree["nodes"][0]
        assert n["disabled"] is True
        assert "clickable" not in n

    def test_full_resource_id_emitted(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="Go" clickable="true" '
            'resource-id="com.app:id/go_btn"/>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert tree["nodes"][0]["id"] == "com.app:id/go_btn"

    def test_no_ref_and_no_bbox_on_mobile(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="X" clickable="true" '
            'bounds="[0,0][100,50]"/>'
            '</hierarchy>'
        )
        n = build_mobile_tree(xml, "android")["nodes"][0]
        assert "ref" not in n
        assert "x" not in n and "w" not in n   # honest: mobile has no bbox in this shape
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dom_capture.py::TestBuildMobileTree -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'playground.dom_capture'`

- [ ] **Step 3: Write the implementation**

Create `playground/dom_capture.py`:

```python
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
    _node_label,
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
    """Parse raw Android/iOS XML into a hierarchical filtered tree, or None.

    NOTE: iOS goes through compress_ios_xml separately for the LLM; for the tree
    we reuse the Android predicates against the WDA XML's android-like attributes.
    If iOS attribute names diverge in practice, the iOS branch degrades to fewer
    surviving nodes — never crashes. (Honest v1 boundary; iOS tree is best-effort.)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dom_capture.py::TestBuildMobileTree -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/dom_capture.py tests/test_dom_capture.py
git commit -m "feat(playground): sidecar hierarchical mobile tree builder (reuses xml predicates, never flattens)"
```

---

### Task 2: Web tree builder wrapper test (the JS is verified live)

**Files:**
- Modify: `playground/dom_capture.py` (already has `build_web_tree` + `_WEB_TREE_JS` from Task 1)
- Test: `tests/test_dom_capture.py`

The injected JS can't be unit-tested in Python (needs a live browser). Test the **wrapper's contract**: passthrough on a well-formed `evaluate` result, `None` on a malformed result, `None` when `evaluate` raises. The JS-correctness is a live-smoke (documented in Task 14).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dom_capture.py`:

```python
class _FakePage:
    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises

    def evaluate(self, _js):
        if self._raises:
            raise self._raises
        return self._result


class TestBuildWebTree:
    def test_passthrough_wellformed_result(self):
        page = _FakePage(result={"nodes": [{"ref": "@1", "class": "button", "children": []}]})
        tree = build_web_tree(page)
        assert tree["platform"] == "web"
        assert tree["nodes"][0]["ref"] == "@1"

    def test_none_when_result_missing_nodes(self):
        assert build_web_tree(_FakePage(result={"oops": 1})) is None

    def test_none_when_result_not_a_dict(self):
        assert build_web_tree(_FakePage(result="not a dict")) is None

    def test_none_when_evaluate_raises(self):
        assert build_web_tree(_FakePage(raises=RuntimeError("page closed"))) is None
```

- [ ] **Step 2: Run tests to verify they fail/pass**

Run: `pytest tests/test_dom_capture.py::TestBuildWebTree -q`
Expected: PASS immediately (the wrapper already exists from Task 1). If any fail, fix `build_web_tree`'s guard logic until green. (This task exists to **pin the wrapper contract** even though the impl predates it.)

- [ ] **Step 3: (no new impl needed — verify ruff clean)**

Run: `ruff check playground/dom_capture.py`
Expected: no errors. Fix any E/F/W/I (e.g., unused imports) until clean.

- [ ] **Step 4: Run the whole new test file**

Run: `pytest tests/test_dom_capture.py -q`
Expected: PASS (12 tests total)

- [ ] **Step 5: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/dom_capture.py tests/test_dom_capture.py
git commit -m "test(playground): pin build_web_tree wrapper contract (degrade-to-None on bad/raised evaluate)"
```

---

### Task 3: Wire capture into the sink (`cli/playground_sink.py`)

**Files:**
- Modify: `cli/playground_sink.py`
- Test: `tests/test_playground_sink.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_playground_sink.py`:

```python
class TestCaptureDomTree:
    def test_capture_returns_none_when_capture_raises(self):
        from cli.playground_sink import PlaygroundSink

        class _Adapter:
            driver = object()

        # platform 'web' path lazy-imports build_web_tree; force a failure by
        # passing an adapter whose driver.evaluate doesn't exist → swallowed → None.
        assert PlaygroundSink.capture_dom_tree(_Adapter(), "web") is None

    def test_has_dom_tree_flag_defaults_false(self):
        from cli.playground_sink import PlaygroundStepEvent

        ev = PlaygroundStepEvent(run_id="r1", step_index=1)
        assert ev.has_dom_tree is False

    def test_disabled_sink_never_posts_tree(self):
        import cli.playground_sink as mod
        from cli.playground_sink import PlaygroundSink

        sink = PlaygroundSink(enabled=False)
        with patch.object(mod.requests, "post") as mock_post:
            sink.push_dom_tree("r1", 1, {"platform": "web", "nodes": []})
            mock_post.assert_not_called()

    def test_push_dom_tree_is_fire_and_forget_and_swallows_errors(self):
        import cli.playground_sink as mod
        from cli.playground_sink import PlaygroundSink

        sink = PlaygroundSink(enabled=True)
        with patch.object(
            mod.requests, "post",
            side_effect=mod.requests.exceptions.ConnectionError("refused"),
        ):
            # Must not raise. Uses a daemon thread; join briefly to let it run.
            sink.push_dom_tree("r1", 1, {"platform": "web", "nodes": []})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_playground_sink.py::TestCaptureDomTree -q`
Expected: FAIL — `AttributeError: ... has no attribute 'capture_dom_tree'` / `has_dom_tree`

- [ ] **Step 3: Write the implementation**

In `cli/playground_sink.py`, add `has_dom_tree` to the model (after the `file_path` field, line ~44):

```python
    file_path: str = ""  # abs path of the generated test file (for "open in IDE")
    has_dom_tree: bool = False  # ⭐ a sidecar DOM tree was captured for this step
```

Add a `_DOM_POST_TIMEOUT` constant next to `_POST_TIMEOUT` (line ~27):

```python
_POST_TIMEOUT = (0.2, 0.25)  # (connect, read) seconds
_DOM_POST_TIMEOUT = (0.2, 0.4)  # tree body is larger; read budget a touch higher
_JOIN_TIMEOUT = 0.3  # seconds; single-step last-frame grace
```

Add two methods to `PlaygroundSink` (after `encode_screenshot`, line ~102):

```python
    @staticmethod
    def capture_dom_tree(adapter, platform: str) -> dict | None:
        """Sidecar hierarchical tree from the SAME raw source the compressors use,
        without touching them. Any failure → None (degrade, never crash the action).

        web:  build_web_tree(adapter.driver)            (Playwright page.evaluate)
        android: build_mobile_tree(driver.dump_hierarchy(), 'android')
        ios:  build_mobile_tree(driver.source(), 'ios')
        """
        try:
            from playground.dom_capture import build_mobile_tree, build_web_tree

            driver = adapter.driver
            if platform == "web":
                return build_web_tree(driver)
            if platform == "android":
                return build_mobile_tree(driver.dump_hierarchy(), "android")
            if platform == "ios":
                return build_mobile_tree(driver.source(), "ios")
            return None
        except Exception as e:
            log.debug(f"[playground-sink] dom capture skip: {e}")
            return None

    def push_dom_tree(self, run_id: str, step_index: int, tree: dict) -> None:
        """Fire-and-forget POST of the captured tree, DECOUPLED from push_step and
        NEVER join-waited — a big tree body must never delay the lean step push or
        the action's exit. Disabled sink → no-op."""
        if not self.enabled:
            return
        threading.Thread(
            target=self._post_dom, args=(run_id, step_index, tree), daemon=True
        ).start()

    def _post_dom(self, run_id: str, step_index: int, tree: dict) -> None:
        try:
            requests.post(
                f"{self.base_url}/api/dom",
                json={"run_id": run_id, "step_index": step_index, "tree": tree},
                timeout=_DOM_POST_TIMEOUT,
            )
        except Exception as e:  # swallow (G5)
            log.debug(f"[playground-sink] dom skip (unreachable): {e}")
```

Now update `build_step_event` to accept and set the flag (signature + the return):

```python
def build_step_event(
    *,
    run_key: str,
    step_index: int,
    action_data: dict,
    result: dict,
    screenshot_b64: str,
    file_path: str = "",
    has_dom_tree: bool = False,
) -> PlaygroundStepEvent:
```

…and add `has_dom_tree=has_dom_tree,` to the `PlaygroundStepEvent(...)` return (after `file_path=...`).

Finally, update `maybe_push_step` to capture the tree, set the flag, and push the tree after the step:

```python
def maybe_push_step(
    sink: "PlaygroundSink",
    *,
    args,
    reporter,
    adapter,
    action_data: dict,
    result: dict,
    step_index: int | None = None,
    file_path: str = "",
) -> None:
    if not sink.enabled:
        return
    try:
        run_key, resolved_index = resolve_playground_run_key(args, reporter)
        idx = step_index if step_index is not None else resolved_index
        tree = sink.capture_dom_tree(adapter, getattr(args, "platform", ""))
        event = build_step_event(
            run_key=run_key,
            step_index=idx,
            action_data=action_data,
            result=result,
            screenshot_b64=PlaygroundSink.encode_screenshot(adapter),
            file_path=file_path,
            has_dom_tree=tree is not None,
        )
        sink.push_step(event)
        if tree is not None:
            sink.push_dom_tree(run_key, idx, tree)  # decoupled, never joined
    except Exception as e:  # never let visualization break the observed action
        log.debug(f"[playground-sink] push skipped: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_playground_sink.py -q`
Expected: PASS (existing tests + 4 new). If `test_capture_returns_none_when_capture_raises` doesn't return None, confirm the lazy import + try/except wraps the `driver` access.

- [ ] **Step 5: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add cli/playground_sink.py tests/test_playground_sink.py
git commit -m "feat(playground): capture+push sidecar DOM tree on the sink path (decoupled, fire-and-forget, has_dom_tree flag)"
```

---

## Phase 2 — Server store + endpoints (Python, TestClient TDD)

### Task 4: Disk-backed, run_key-keyed tree store + `POST /api/dom`

**Files:**
- Modify: `playground/app.py`
- Test: `tests/test_playground_app.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_playground_app.py`:

```python
class TestDomStore:
    def test_post_dom_persists_and_get_returns_it(self, client, tmp_path):
        app_module._DOM_DIR = tmp_path  # redirect store to a temp dir
        app_module._dom_index.clear()
        tree = {"platform": "web", "nodes": [{"ref": "@1", "class": "button", "children": []}]}
        r = client.post("/api/dom", json={"run_id": "s1", "step_index": 2, "tree": tree})
        assert r.status_code == 200 and r.json()["ok"] is True
        got = client.get("/api/run/s1/step/2/dom")
        assert got.status_code == 200
        assert got.json()["nodes"][0]["ref"] == "@1"

    def test_get_absent_returns_404(self, client, tmp_path):
        app_module._DOM_DIR = tmp_path
        app_module._dom_index.clear()
        assert client.get("/api/run/nope/step/9/dom").status_code == 404

    def test_lru_evicts_oldest_run_dir(self, client, tmp_path):
        app_module._DOM_DIR = tmp_path
        app_module._dom_index.clear()
        app_module._MAX_DOM_RUNS = 2
        for rid in ("a", "b", "c"):  # 3 runs, cap 2 → 'a' evicted
            client.post("/api/dom", json={"run_id": rid, "step_index": 1,
                                          "tree": {"platform": "web", "nodes": []}})
        assert client.get("/api/run/a/step/1/dom").status_code == 404
        assert client.get("/api/run/c/step/1/dom").status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_playground_app.py::TestDomStore -q`
Expected: FAIL — 404/AttributeError (`_DOM_DIR`/`_dom_index` undefined, `/api/dom` missing)

- [ ] **Step 3: Write the implementation**

In `playground/app.py`, add imports + store near the top state (after `_step_log` block, line ~81):

```python
import tempfile
from collections import OrderedDict as _OrderedDict

# ⭐ DOM tree store (Brain's Eye View). Trees are 25–80KB — too big for a RAM LRU
# (20×500×80KB ≈ 800MB), so the RESIDENT server persists them to disk keyed by
# run_key (the cross-process-stable playground key — NOT reporter.run_id, which
# differs per --action process). RAM holds only a tiny index: run_key → set(steps).
_DOM_DIR = Path(tempfile.gettempdir()) / "screenforge_playground_dom"
_MAX_DOM_RUNS = 5  # LRU cap on distinct run dirs (disk is cheap; ~40MB/run worst)
_dom_index: "_OrderedDict[str, set]" = _OrderedDict()


def _dom_run_dir(run_id: str) -> Path:
    safe = "".join(c for c in run_id if c.isalnum() or c in ("-", "_", "."))[:120] or "run"
    return _DOM_DIR / safe


def _dom_evict_if_needed() -> None:
    while len(_dom_index) > _MAX_DOM_RUNS:
        old_key, _ = _dom_index.popitem(last=False)
        d = _dom_run_dir(old_key)
        if d.exists():
            for f in d.glob("*.json"):
                f.unlink(missing_ok=True)
            try:
                d.rmdir()
            except OSError:
                pass
```

Add the POST endpoint (after `post_step`, line ~175):

```python
@app.post("/api/dom")
async def post_dom(request: Request):
    """Persist a sidecar DOM tree for (run_id=run_key, step_index). Fire-and-forget
    from the sink; the server owns the disk path (the producer can't — N session
    processes share one run_key but have different reporter dirs)."""
    body = await request.json()
    run_id = str(body.get("run_id", "default"))
    step_index = int(body.get("step_index", 0) or 0)
    tree = body.get("tree")
    if not isinstance(tree, dict):
        return {"ok": False, "error": "no tree"}
    d = _dom_run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"step_{step_index:03d}.json").write_text(
        json.dumps(tree, ensure_ascii=False)
    )
    steps = _dom_index.setdefault(run_id, set())
    steps.add(step_index)
    _dom_index.move_to_end(run_id)  # LRU: most-recently-written run to the tail
    _dom_evict_if_needed()
    return {"ok": True}
```

Add the GET endpoint (next to `get_run_steps`, line ~185):

```python
@app.get("/api/run/{run_id}/step/{step_index}/dom")
async def get_run_step_dom(run_id: str, step_index: int):
    """Return the stored hierarchical tree for a step, or 404 if absent (not landed
    yet / evicted / capture returned None / mobile). The frontend treats 404 as a
    quiet 'tree unavailable for this step'."""
    from fastapi.responses import JSONResponse

    path = _dom_run_dir(run_id) / f"step_{step_index:03d}.json"
    if not path.is_file():
        return JSONResponse({"error": "no tree for this step"}, status_code=404)
    return JSONResponse(json.loads(path.read_text()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_playground_app.py::TestDomStore -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/app.py tests/test_playground_app.py
git commit -m "feat(playground): disk-backed run_key-keyed DOM tree store + POST /api/dom + GET .../dom (LRU=5)"
```

---

### Task 5: `has_dom_tree` SSE passthrough (confirm + pin)

**Files:**
- Modify: `playground/app.py` (only if the passthrough doesn't already carry it)
- Test: `tests/test_playground_app.py`

`post_step` already broadcasts `{**body, "screenshot_b64": b64}`. Since `has_dom_tree` is part of the step event `model_dump()`, it flows through `body` automatically. This task **pins** that with a test so a future refactor can't silently drop it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_playground_app.py`:

```python
class TestHasDomTreePassthrough:
    def test_step_event_carries_has_dom_tree_to_sse(self, client):
        # Subscribe to SSE, post a step with has_dom_tree, assert it's broadcast.
        import json as _json

        with client.stream("GET", "/api/events") as stream:
            body = _step_body(run_id="r1", step_index=1)
            body["has_dom_tree"] = True
            client.post("/api/step", json=body)
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    evt = _json.loads(line[6:])
                    if evt.get("type") == "step":
                        assert evt.get("has_dom_tree") is True
                        break
```

- [ ] **Step 2: Run test to verify it passes (or fails meaningfully)**

Run: `pytest tests/test_playground_app.py::TestHasDomTreePassthrough -q`
Expected: PASS (passthrough already works). If it FAILS (a stricter `post_step` strips unknown keys), add `has_dom_tree` explicitly to the `push_event("step", {...})` payload in `post_step`:
```python
    push_event("step", {**body, "screenshot_b64": b64, "has_dom_tree": body.get("has_dom_tree", False)})
```

- [ ] **Step 3: Run the full playground test suite**

Run: `pytest tests/test_playground_app.py tests/test_playground_sink.py tests/test_dom_capture.py -q`
Expected: PASS (all)

- [ ] **Step 4: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/app.py tests/test_playground_app.py
git commit -m "test(playground): pin has_dom_tree SSE passthrough"
```

---

## Phase 3 — Frontend (single-file `playground/index.html`)

> **Frontend verification model (all Phase-3 tasks):** no JS unit harness exists in this repo. Each task verifies by: (1) `python -c "import playground.app"` + opening `http://127.0.0.1:7860` with the offline demo feed, and (2) a per-task manual checklist. The offline feed (`USE_LIVE_BACKEND=false`, `startPrototypeFeed()`) is extended in Task 9 to emit a fake tree so the panel animates with zero backend. Commit after the checklist passes.

### Task 6: CSS — drawer shell, tree rows, flag chips, bbox overlay, animations

**Files:**
- Modify: `playground/index.html` (insert a CSS block before the closing `</style>`; find it with `grep -n "</style>" playground/index.html | head -1`)

- [ ] **Step 1: Insert the CSS block**

Insert immediately before the **first** `</style>`:

```css
/* ============================ BRAIN'S EYE VIEW (DOM TREE) ============================ */
/* Right-edge collapsible drawer; pinnable to a fixed column at ≥1360px. Built only on
   existing forge tokens — no new colors/fonts. */
#domTab {                            /* always-visible toggle strip on the workspace edge */
  position: absolute; top: 50%; right: 0; transform: translateY(-50%);
  width: 22px; height: 132px; z-index: 30;
  background: var(--bg-3); border: 1px solid var(--line); border-right: none;
  border-radius: var(--r-sm) 0 0 var(--r-sm);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; cursor: pointer; color: var(--text-dim);
  transition: color .15s, background .15s;
}
#domTab:hover { color: var(--text-hi); background: var(--bg-4); }
#domTab .tab-label { writing-mode: vertical-rl; font: 9px/1 var(--font-mono);
  letter-spacing: .14em; text-transform: uppercase; }
#domTab .tab-pip { width: 5px; height: 5px; border-radius: 50%; background: var(--line-strong); }
#domTab.has-data .tab-pip { background: var(--ember); box-shadow: 0 0 6px var(--ember-glow); }

#domDrawer {
  position: absolute; top: 0; right: 0; height: 100%; width: 292px; z-index: 40;
  background: var(--bg-1); border-left: 1px solid var(--line);
  box-shadow: var(--shadow-panel);
  transform: translateX(100%); transition: transform .22s cubic-bezier(.4,0,.2,1);
  display: flex; flex-direction: column;
}
#domDrawer.open { transform: translateX(0); }
.workspace.drawer-open .right-stack { filter: brightness(.85); transition: filter .22s; }
.workspace.drawer-pinned #domDrawer { position: relative; transform: none; box-shadow: none; }

.dom-head { display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-bottom: 1px solid var(--line); flex: 0 0 auto; }
.dom-head .title { font: 600 11px/1 var(--font-mono); letter-spacing: .1em;
  text-transform: uppercase; color: var(--text-hi); }
.dom-diff { display: flex; gap: 6px; font: 10px/1 var(--font-mono); margin-left: auto; }
.dom-diff .add { color: var(--green); } .dom-diff .rem { color: var(--red); }
.dom-diff .chg { color: var(--amber); }
.dom-diff span { cursor: pointer; }
.dom-head button { background: none; border: none; color: var(--text-dim);
  cursor: pointer; font-size: 13px; padding: 2px; }
.dom-head button:hover { color: var(--text-hi); }
.dom-search { padding: 6px 10px; border-bottom: 1px solid var(--line-soft); }
.dom-search input { width: 100%; background: var(--bg-3); border: 1px solid var(--line);
  border-radius: var(--r-sm); color: var(--text); font: 11px var(--font-mono);
  padding: 4px 7px; }
.dom-search input:focus { outline: 2px solid var(--blue); outline-offset: 1px; border-color: var(--blue); }
.dom-notice { font: 9.5px var(--font-mono); color: var(--text-faint);
  background: rgba(251,191,36,0.05); border-bottom: 1px solid var(--line-soft);
  padding: 5px 10px; display: flex; gap: 6px; align-items: center; }
.dom-notice button { margin-left: auto; }

#treeContainer { flex: 1 1 auto; overflow: auto; padding: 4px 0 12px; }
#treeContainer ul { list-style: none; margin: 0; padding: 0; }
.tree-node-row { display: flex; align-items: center; gap: 5px; min-height: 24px;
  padding: 1px 8px 1px 0; cursor: default; border-left: 2px solid transparent;
  font: 11.5px var(--font-mono); color: var(--text); }
.tree-node-row:hover { background: var(--bg-4); border-left-color: var(--blue); }
.workspace[data-platform="android"] .tree-node-row:hover,
.workspace[data-platform="ios"] .tree-node-row:hover { border-left-color: var(--amber); }
.tree-chevron { width: 12px; flex: 0 0 12px; color: var(--text-faint);
  transition: transform .15s ease; font-size: 9px; }
.tree-chevron.leaf { visibility: hidden; }
li[aria-expanded="true"] > .tree-node-row .tree-chevron { transform: rotate(90deg); }
li[aria-expanded="false"] > ul { display: none; }
.tree-class { font-size: 9px; padding: 1px 4px; border: 1px solid var(--line);
  border-radius: var(--r-sm); background: var(--bg-3); }
.tree-class.interactive { color: var(--blue); }
.tree-class.text { color: var(--text-dim); }
.tree-class.layout { color: var(--text-faint); }
.tree-scope { color: var(--text-faint); margin-right: 4px; }
.tree-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px; }
.tree-label.placeholder { font-style: italic; color: var(--text-faint); }
.tree-dup { font-size: 8.5px; color: var(--text-faint); vertical-align: super; }
.tree-ref { color: var(--purple); background: rgba(165,180,252,0.08);
  border: 1px solid rgba(165,180,252,0.20); font-size: 9px; padding: 1px 4px;
  border-radius: var(--r-sm); cursor: pointer; margin-left: auto; }
.tree-ref:hover { background: rgba(165,180,252,0.16); border-color: rgba(165,180,252,0.40); }
.tree-flag { font-size: 8.5px; padding: 1px 4px; border-radius: var(--r-sm); margin-left: 4px; }
.tree-flag.disabled { color: var(--amber); background: rgba(251,191,36,0.08);
  border: 1px solid rgba(251,191,36,0.22); }
.tree-flag.inert { color: var(--text-faint); border: 1px dashed var(--line-strong); background: transparent; }

/* current target: same ember left-rail as action-item.selected */
.tree-node-row.is-target {
  background: linear-gradient(90deg, rgba(255,120,73,0.13), rgba(255,120,73,0.04) 65%, transparent);
  border-left: 2.5px solid var(--ember);
  box-shadow: inset 2px 0 10px rgba(255,120,73,0.12);
}
.tree-node-row.is-target .tree-ref { color: var(--ember-soft);
  background: rgba(255,120,73,0.08); border-color: rgba(255,120,73,0.30); }

/* bbox overlay over the screenshot */
#domBboxOverlay { position: absolute; pointer-events: none; border: 1.5px solid var(--blue);
  background: rgba(96,165,250,0.08); border-radius: 3px; opacity: 0;
  transition: opacity .12s; z-index: 5; }
#domBboxOverlay.show { opacity: 1; }
#domBboxOverlay.target { border-color: var(--ember); background: rgba(255,120,73,0.10);
  box-shadow: 0 0 0 1px var(--ember-glow); }

/* reconciler animations */
@keyframes dom-node-in { from { opacity: 0; background: rgba(96,165,250,0.08); }
  to { opacity: 1; background: transparent; } }
.dom-node-added .tree-node-row { animation: dom-node-in 250ms cubic-bezier(.2,.7,.2,1) both; }
.dom-node-out { transition: opacity 180ms ease, max-height 200ms ease;
  opacity: 0 !important; max-height: 0 !important; overflow: hidden; pointer-events: none; }
@keyframes dom-field-pulse { 0%,100% { color: inherit; } 40% { color: var(--amber); } }
.dom-field-changed { animation: dom-field-pulse 400ms ease both; }
.tree-mark { background: rgba(251,191,36,0.22); border-radius: 2px; }   /* search hit */
@media (max-width: 1359px) { .workspace.drawer-pinned #domDrawer { position: absolute; } }
```

- [ ] **Step 2: Verify the page still loads (CSS doesn't break layout)**

Run: `python -c "import playground.app"` then start `screenforge --playground` (or `python -m playground.app`) and open `http://127.0.0.1:7860`.
Manual check: the existing 3-panel + filmstrip layout is **unchanged** (the new CSS targets only `#domDrawer`/`#domTab`/`.tree-*` which don't exist in the DOM yet — so nothing visually changes). No console errors.

- [ ] **Step 3: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): forge-token CSS for the Brain's Eye View drawer + tree rows + bbox overlay"
```

---

### Task 7: HTML structure — drawer, tab, diff badge, search, overlay div

**Files:**
- Modify: `playground/index.html`

- [ ] **Step 1: Add the bbox overlay div inside the screenshot panel-body**

Find the screenshot panel body: `grep -n 'class="panel-body" style="position:relative;"' playground/index.html` (≈ line 1777). Immediately after that opening `<div class="panel-body" style="position:relative;">`, add:

```html
      <div id="domBboxOverlay" aria-hidden="true"></div>
```

- [ ] **Step 2: Add the drawer + tab markup at the end of the workspace**

Find the workspace close. Run: `grep -n '</main>' playground/index.html | head -1`. Immediately **before** `</main>`, insert:

```html
  <!-- ============== BRAIN'S EYE VIEW (DOM TREE) ============== -->
  <div id="domTab" role="button" tabindex="0" aria-label="Toggle DOM tree (B)" title="DOM tree — Brain's Eye View (B)">
    <span class="tab-pip"></span>
    <span class="tab-label">Tree</span>
  </div>
  <aside id="domDrawer" aria-label="Brain's Eye View — DOM tree" aria-hidden="true">
    <div class="dom-head">
      <span class="title">Brain's Eye View</span>
      <span class="dom-diff" id="domDiff" hidden>
        <span class="add" id="domAdd" title="added">+0</span>
        <span class="rem" id="domRem" title="removed">−0</span>
        <span class="chg" id="domChg" title="changed">~0</span>
      </span>
      <button id="domPin" title="Pin to a fixed column">⊟</button>
      <button id="domClose" title="Close (B)">✕</button>
    </div>
    <div class="dom-search">
      <input type="search" id="domSearch" role="searchbox" placeholder="filter elements…"
             aria-label="Search DOM elements" aria-controls="treeContainer" />
    </div>
    <div class="dom-notice" id="domNotice" hidden>
      <span>No bbox on Android/iOS — screenshot overlay unavailable.</span>
      <button id="domNoticeDismiss" title="Dismiss">✕</button>
    </div>
    <ul id="treeContainer" role="tree" aria-label="DOM perception tree" tabindex="0"></ul>
    <div class="sr-only" id="treeAriaLive" aria-live="polite"></div>
  </aside>
```

> If `.sr-only` isn't defined in the file, add to the CSS block: `.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}`. (Check first: `grep -n '\.sr-only' playground/index.html`.)

- [ ] **Step 3: Set `data-platform` on the workspace for the mobile-degrade CSS**

Confirm `setPlatform(p)` exists (line ≈ 2300). At the end of `setPlatform`, add a line so the CSS hover-rail color and notice can key off platform:
```js
  document.querySelector('.workspace').dataset.platform = p;
```

- [ ] **Step 4: Verify the page loads with the drawer closed**

Open `http://127.0.0.1:7860`. The `Tree` tab is visible on the right edge; the drawer is off-screen (closed). No layout shift to the existing panels. No console errors. (Tab does nothing yet — JS comes next.)

- [ ] **Step 5: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): DOM tree drawer/tab/search/diff-badge markup + bbox overlay div"
```

---

### Task 8: JS — drawer open/close/pin + localStorage + hotkey `B`

**Files:**
- Modify: `playground/index.html` (add a new `<script>`-level block; place it near the IDE-button block, after `initThemeToggle`, found via `grep -n "initThemeToggle" playground/index.html`)

- [ ] **Step 1: Add the drawer controller**

Insert after the theme-toggle IIFE:

```js
/* ====================== BRAIN'S EYE VIEW — drawer controller ====================== */
const domEls = {
  tab:    document.getElementById('domTab'),
  drawer: document.getElementById('domDrawer'),
  close:  document.getElementById('domClose'),
  pin:    document.getElementById('domPin'),
  search: document.getElementById('domSearch'),
  tree:   document.getElementById('treeContainer'),
  diff:   document.getElementById('domDiff'),
  add:    document.getElementById('domAdd'),
  rem:    document.getElementById('domRem'),
  chg:    document.getElementById('domChg'),
  notice: document.getElementById('domNotice'),
  noticeDismiss: document.getElementById('domNoticeDismiss'),
  live:   document.getElementById('treeAriaLive'),
  workspace: document.querySelector('.workspace'),
};
const DOM_OPEN_KEY = 'screenforge.playground.domtree.open';
const DOM_PIN_KEY  = 'screenforge.playground.domtree.pinned';
const DOM_NOBBOX_KEY = 'screenforge.playground.domtree.nobboxdismissed';

function domDrawerOpen(open) {
  domEls.drawer.classList.toggle('open', open);
  domEls.drawer.setAttribute('aria-hidden', String(!open));
  domEls.workspace.classList.toggle('drawer-open', open);
  try { localStorage.setItem(DOM_OPEN_KEY, open ? '1' : '0'); } catch (e) {}
  if (open) onDrawerOpened();   // defined in Task 9 (lazy fetch current step's tree)
}
function domDrawerToggle() { domDrawerOpen(!domEls.drawer.classList.contains('open')); }

function domDrawerPin(pinned) {
  const canPin = window.innerWidth >= 1360;
  const eff = pinned && canPin;
  domEls.workspace.classList.toggle('drawer-pinned', eff);
  try { localStorage.setItem(DOM_PIN_KEY, eff ? '1' : '0'); } catch (e) {}
}

domEls.tab.addEventListener('click', domDrawerToggle);
domEls.tab.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); domDrawerToggle(); }
});
domEls.close.addEventListener('click', () => domDrawerOpen(false));
domEls.pin.addEventListener('click', () =>
  domDrawerPin(!domEls.workspace.classList.contains('drawer-pinned')));
domEls.noticeDismiss.addEventListener('click', () => {
  domEls.notice.hidden = true;
  try { localStorage.setItem(DOM_NOBBOX_KEY, '1'); } catch (e) {}
});
document.addEventListener('keydown', e => {
  const t = e.target.tagName;
  if (e.key === 'b' && t !== 'INPUT' && t !== 'TEXTAREA' && !e.metaKey && !e.ctrlKey) {
    e.preventDefault(); domDrawerToggle();
  }
});
// restore persisted state
try {
  if (localStorage.getItem(DOM_PIN_KEY) === '1') domDrawerPin(true);
  if (localStorage.getItem(DOM_OPEN_KEY) === '1') domDrawerOpen(true);
} catch (e) {}
```

- [ ] **Step 2: Add a temporary stub for `onDrawerOpened` (replaced in Task 9)**

Just above the controller block, add:
```js
function onDrawerOpened() { /* Task 9 fills this with lazy tree fetch */ }
```

- [ ] **Step 3: Verify drawer interactions**

Open the page. Manual checklist:
- Click the `Tree` tab → drawer slides in (220ms); right-stack dims. Click `✕` or press `B` → slides out.
- Click `⊟` pin (on a ≥1360px window) → drawer becomes a fixed column (no dim). Reload → state persists.
- Press `B` while focus is in a text field → does NOT toggle (guard works).

- [ ] **Step 4: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): DOM drawer open/close/pin + hotkey B + localStorage persistence"
```

---

### Task 9: JS — renderer (nested data → `<li>` tree) + on-demand fetch + demo feed

**Files:**
- Modify: `playground/index.html`

- [ ] **Step 1: Add the renderer + fetch + per-step tree state**

Insert after the drawer controller block:

```js
/* ====================== BRAIN'S EYE VIEW — renderer + fetch ====================== */
const INTERACTIVE_TAGS = new Set(['button','a','input','select','textarea',
  'Button','ImageButton','CheckBox','EditText','Switch','RadioButton']);
const TEXT_TAGS = new Set(['label','span','p','h1','h2','h3','h4','h5','h6','TextView','StaticText']);

function classCategory(cls) {
  if (INTERACTIVE_TAGS.has(cls)) return 'interactive';
  if (TEXT_TAGS.has(cls)) return 'text';
  return 'layout';
}
function bestLabel(node) {
  return node.text || node.desc || node.id_short || node.id || '';
}
function copyLocator(node, platform) {
  let loc;
  if (platform === 'web') {
    if (node.id) loc = '#' + node.id;
    else if (node.desc) loc = `[aria-label="${node.desc}"]`;
    else if (node.text) loc = `text=${node.text}`;
    else loc = node.ref || '';
  } else {
    if (node.id) loc = `id=${node.id}`;
    else if (node.text) loc = `text=${node.text}`;
    else if (node.desc) loc = `desc=${node.desc}`;
    else loc = '';
  }
  if (loc) { try { navigator.clipboard.writeText(loc); } catch (e) {} }
  return loc;
}

// Build one <li role=treeitem> (row + nested <ul> of children), recursively.
function createTreeLi(node, depth, siblingIndex, platform, key) {
  const li = document.createElement('li');
  li.setAttribute('role', 'treeitem');
  li.setAttribute('aria-level', String(depth + 1));
  li.dataset.domKey = key;
  li.tabIndex = -1;
  const hasKids = node.children && node.children.length > 0;
  if (hasKids) li.setAttribute('aria-expanded', depth < 1 ? 'true' : 'false');

  const row = document.createElement('div');
  row.className = 'tree-node-row';
  row.style.paddingLeft = (12 + depth * 16) + 'px';
  const cls = node.class || '?';
  const lbl = bestLabel(node);
  row.innerHTML =
    `<span class="tree-chevron${hasKids ? '' : ' leaf'}">▶</span>` +
    `<span class="tree-class ${classCategory(cls)}">${escapeHtml(cls)}</span>` +
    (node.scope ? `<span class="tree-scope">[${escapeHtml(node.scope)}]</span>` : '') +
    `<span class="tree-label${lbl ? '' : ' placeholder'}">${escapeHtml(lbl || '(no label)')}</span>` +
    (node.dup_index ? `<span class="tree-dup">#${node.dup_index}</span>` : '') +
    (platform === 'web' && node.ref ? `<span class="tree-ref" title="Copy locator">${node.ref}</span>` : '') +
    (node.disabled ? `<span class="tree-flag disabled">DISABLED</span>` : '') +
    (node.inert ? `<span class="tree-flag inert">INERT</span>` : '');
  li.appendChild(row);

  // chevron toggles expand/collapse
  const chev = row.querySelector('.tree-chevron');
  if (hasKids) {
    row.addEventListener('click', e => {
      if (e.target.classList.contains('tree-ref')) return;
      const exp = li.getAttribute('aria-expanded') === 'true';
      li.setAttribute('aria-expanded', String(!exp));
    });
  }
  // ref badge copies locator
  const ref = row.querySelector('.tree-ref');
  if (ref) ref.addEventListener('click', e => {
    e.stopPropagation();
    const loc = copyLocator(node, platform);
    if (loc) { const o = ref.textContent; ref.textContent = 'copied'; setTimeout(() => ref.textContent = o, 1100); }
  });
  // hover → bbox overlay (Task 11 defines drawBbox/clearBbox)
  row.addEventListener('mouseenter', () => { if (node.x != null) drawBbox(node, false); });
  row.addEventListener('mouseleave', () => clearBbox());

  if (hasKids) {
    const ul = document.createElement('ul');
    node.children.forEach((c, i) => ul.appendChild(
      createTreeLi(c, depth + 1, i, platform, key + '/' + childKey(c, depth + 1, i, platform))));
    li.appendChild(ul);
  }
  return li;
}

// stable key per node: web uses ref; mobile uses a djb2 composite (depth+sibling
// separates same-named rows — the scope/dup_index intent).
function djb2(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h) ^ str.charCodeAt(i);
  return (h >>> 0).toString(16).padStart(8, '0');
}
function childKey(node, depth, siblingIndex, platform) {
  if (platform === 'web' && node.ref) return node.ref;
  return djb2((node.class || 'x') + '|' +
    (node.text || node.desc || node.id_short || 'ø').slice(0, 40) + '|d' + depth + '|s' + siblingIndex);
}

// Full (re)render — used on first show and on full-navigation steps.
function renderTreeFull(tree) {
  domEls.tree.innerHTML = '';
  if (!tree || !tree.nodes) return;
  const platform = tree.platform || 'web';
  tree.nodes.forEach((n, i) => domEls.tree.appendChild(
    createTreeLi(n, 0, i, platform, childKey(n, 0, i, platform))));
  domEls.notice.hidden = !(platform !== 'web') ||
    (localStorage.getItem(DOM_NOBBOX_KEY) === '1');
}

// per-step tree cache (last 50) + on-demand fetch
const _treeCache = new Map();   // "runId#stepIndex" → tree
let _treeShownStep = null;

async function fetchTree(runId, stepIndex) {
  const k = runId + '#' + stepIndex;
  if (_treeCache.has(k)) return _treeCache.get(k);
  try {
    const r = await fetch(`/api/run/${encodeURIComponent(runId)}/step/${stepIndex}/dom`);
    if (!r.ok) return null;        // 404 = unavailable for this step (quiet)
    const tree = await r.json();
    _treeCache.set(k, tree);
    if (_treeCache.size > 50) _treeCache.delete(_treeCache.keys().next().value);
    return tree;
  } catch (e) { return null; }
}

async function showTreeForStep(runId, stepIndex, targetNodeRefOrKey) {
  if (!domEls.drawer.classList.contains('open')) return;   // lazy: only when visible
  const tree = await fetchTree(runId, stepIndex);
  if (!tree) { return; }
  if (_treeShownStep === null) renderTreeFull(tree);
  else reconcileTree(tree);          // Task 10
  _treeShownStep = stepIndex;
  highlightTarget(tree, targetNodeRefOrKey);   // Task 11
}

function onDrawerOpened() {
  // Lazy fetch the current step's tree the first time the drawer opens.
  if (_currentRunId && state.steps.length) {
    const last = state.steps[state.steps.length - 1];
    showTreeForStep(_currentRunId, last.step_index, last.locator_value);
  }
}
```

- [ ] **Step 2: Add stubs for not-yet-defined functions (filled in Tasks 10–11)**

Above the renderer block, add:
```js
function reconcileTree(tree) { renderTreeFull(tree); }   // Task 10 replaces with keyed diff
function drawBbox(node, isTarget) {}                      // Task 11
function clearBbox() {}                                   // Task 11
function highlightTarget(tree, ref) {}                    // Task 11
```

- [ ] **Step 3: Extend the offline demo feed to emit a fake tree**

Find `startPrototypeFeed()` (≈ line 2819). Inside it, after the fake steps are defined, add a fake tree fetch shim so the panel works offline. Locate the `fetchTree` usage path — simplest: before `startPrototypeFeed`, override `fetchTree` when `USE_LIVE_BACKEND` is false:

```js
if (!USE_LIVE_BACKEND) {
  const _demoTree = { platform: 'web', nodes: [
    { ref:'@1', class:'form', text:'Sign in', children: [
      { ref:'@2', class:'input', desc:'Email', clickable:true, x:120,y:180,w:240,h:36, children:[] },
      { ref:'@3', class:'input', type:'password', desc:'Password', clickable:true, x:120,y:230,w:240,h:36, children:[] },
      { ref:'@4', class:'button', text:'Log in', clickable:true, x:120,y:290,w:240,h:40, children:[] },
    ]},
  ]};
  window.fetchTree = async () => _demoTree;   // demo: same tree every step
}
```

- [ ] **Step 4: Verify the renderer offline**

Temporarily set `USE_LIVE_BACKEND = false` (line ≈ 1252), reload. Open the drawer → the fake sign-in tree renders: `form ▸ (input Email, input Password, button Log in)`, depth-0/1 expanded, chevrons rotate on click, `@N` badges present, hovering a node does nothing yet (bbox is Task 11). **Revert `USE_LIVE_BACKEND = true` before committing.**

- [ ] **Step 5: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): DOM tree renderer (nested li tree, copy-locator, stable keys) + on-demand fetch + demo tree"
```

---

### Task 10: JS — keyed reconciler (no flash, preserve expand/scroll)

**Files:**
- Modify: `playground/index.html`

- [ ] **Step 1: Replace the `reconcileTree` stub with the real keyed reconciler**

Replace `function reconcileTree(tree) { renderTreeFull(tree); }` with:

```js
/* Keyed reconciler: patch the tree in place so expand/collapse + scroll + search
   survive a per-step update, and only added/removed/changed nodes animate. Full
   navigation (>80% new keys) falls back to a clean full render for that step. */
function flattenWithKeys(nodes, depth, platform, parentKey, out) {
  nodes.forEach((n, i) => {
    const key = (parentKey ? parentKey + '/' : '') + childKey(n, depth, i, platform);
    out.push({ node: n, depth, key, parentKey });
    if (n.children && n.children.length) flattenWithKeys(n.children, depth + 1, platform, key, out);
  });
  return out;
}

function reconcileTree(tree) {
  const platform = tree.platform || 'web';
  const incoming = flattenWithKeys(tree.nodes || [], 0, platform, '', []);
  const incomingKeys = new Set(incoming.map(x => x.key));

  const existing = new Map();
  domEls.tree.querySelectorAll('li[data-dom-key]').forEach(li => existing.set(li.dataset.domKey, li));

  // full-navigation heuristic: mostly-new keys → clean render
  const newCount = incoming.filter(x => !existing.has(x.key)).length;
  if (existing.size && incoming.length && newCount / incoming.length > 0.8) {
    renderTreeFull(tree);
    domEls.add.textContent = '+' + incoming.length;
    domEls.rem.textContent = '−' + existing.size;
    domEls.chg.textContent = '~0';
    domEls.diff.hidden = false;
    return;
  }

  let added = 0, removed = 0, changed = 0;

  // removals: keys no longer present
  existing.forEach((li, key) => {
    if (!incomingKeys.has(key)) {
      li.classList.add('dom-node-out');
      removed++;
      setTimeout(() => li.remove(), 220);
    }
  });

  // adds + in-place patches (skip the reorder complexity in v1: only add brand-new
  // nodes under their parent's <ul>; existing nodes keep their place — correct for
  // in-page interactions where structure is stable and only labels/flags change)
  incoming.forEach(({ node, depth, key, parentKey }, i) => {
    const li = existing.get(key);
    if (li) {
      if (patchNodeLi(li, node, platform)) changed++;
    } else {
      const newLi = createTreeLi(node, depth, i, platform, key);
      newLi.classList.add('dom-node-added');
      const parentLi = parentKey ? domEls.tree.querySelector(`li[data-dom-key="${CSS.escape(parentKey)}"]`) : null;
      const ul = parentLi ? (parentLi.querySelector(':scope > ul') || _ensureChildUl(parentLi)) : domEls.tree;
      ul.appendChild(newLi);
      added++;
      setTimeout(() => newLi.classList.remove('dom-node-added'), 300);
    }
  });

  domEls.add.textContent = '+' + added;
  domEls.rem.textContent = '−' + removed;
  domEls.chg.textContent = '~' + changed;
  domEls.diff.hidden = false;
}

function _ensureChildUl(parentLi) {
  let ul = parentLi.querySelector(':scope > ul');
  if (!ul) { ul = document.createElement('ul'); parentLi.appendChild(ul);
    if (!parentLi.hasAttribute('aria-expanded')) parentLi.setAttribute('aria-expanded', 'true'); }
  return ul;
}

// Patch ONLY display fields; NEVER touch aria-expanded / child <ul> / scroll.
function patchNodeLi(li, node, platform) {
  const row = li.querySelector(':scope > .tree-node-row');
  if (!row) return false;
  let changed = false;
  const labelEl = row.querySelector('.tree-label');
  const newLabel = bestLabel(node) || '(no label)';
  if (labelEl && labelEl.textContent !== newLabel) {
    labelEl.textContent = newLabel;
    labelEl.classList.add('dom-field-changed');
    setTimeout(() => labelEl.classList.remove('dom-field-changed'), 400);
    changed = true;
  }
  // disabled/inert flag sync
  syncFlag(row, 'disabled', node.disabled, 'DISABLED');
  syncFlag(row, 'inert', node.inert, 'INERT');
  return changed;
}
function syncFlag(row, cls, on, text) {
  let el = row.querySelector('.tree-flag.' + cls);
  if (on && !el) { el = document.createElement('span'); el.className = 'tree-flag ' + cls;
    el.textContent = text; row.appendChild(el); }
  else if (!on && el) { el.remove(); }
}
```

- [ ] **Step 2: Verify reconciliation preserves state offline**

Set `USE_LIVE_BACKEND = false`. Modify the demo `fetchTree` to return a tree whose `button` label changes after a few steps (e.g. step-dependent). Reload, open drawer, expand a node, scroll, then let the feed advance: the expanded/scroll state **survives**; only the changed label pulses amber; the `+N −N ~N` badge updates. **Revert `USE_LIVE_BACKEND = true`.**

- [ ] **Step 3: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): keyed tree reconciler — patch in place, preserve expand/scroll, diff badge"
```

---

### Task 11: JS — bbox overlay + target highlight + cross-panel

**Files:**
- Modify: `playground/index.html`

- [ ] **Step 1: Replace the bbox/highlight stubs with real implementations**

Replace the four stubs from Task 9 Step 2:

```js
/* ---- bbox overlay on the screenshot (web only; honest no-op on mobile) ---- */
const _bbox = document.getElementById('domBboxOverlay');
function drawBbox(node, isTarget) {
  if (state.platform !== 'web' || node.x == null) return;
  const frame = els.shotFrame;
  const img = els.shotImg;
  if (!frame || frame.style.display === 'none' || !img.naturalWidth) return;
  // captured at 1280px viewport width; scale to the displayed image box
  const dispW = img.clientWidth, dispH = img.clientHeight;
  const scale = dispW / 1280;
  const rectFrame = frame.getBoundingClientRect();
  const rectBody = _bbox.parentElement.getBoundingClientRect();
  const offX = rectFrame.left - rectBody.left;
  const offY = rectFrame.top - rectBody.top;
  _bbox.style.left = (offX + node.x * scale) + 'px';
  _bbox.style.top  = (offY + node.y * scale) + 'px';
  _bbox.style.width  = (node.w * scale) + 'px';
  _bbox.style.height = (node.h * scale) + 'px';
  _bbox.classList.toggle('target', !!isTarget);
  _bbox.classList.add('show');
}
function clearBbox() { _bbox.classList.remove('show'); }

/* ---- target element: ember-light it, expand ancestors, scroll into view, bbox ---- */
function findNodeByTarget(tree, targetVal) {
  // match the step's locator_value against text/desc/id/ref
  let found = null;
  (function walk(nodes) {
    for (const n of nodes) {
      if (found) return;
      if (targetVal && (n.text === targetVal || n.desc === targetVal ||
          n.id === targetVal || n.ref === targetVal)) { found = n; return; }
      if (n.children) walk(n.children);
    }
  })(tree.nodes || []);
  return found;
}
function highlightTarget(tree, targetVal) {
  domEls.tree.querySelectorAll('.tree-node-row.is-target').forEach(r => r.classList.remove('is-target'));
  const node = findNodeByTarget(tree, targetVal);
  if (!node) return;
  // locate its rendered <li> by matching ref (web) or label
  let li = null;
  if (node.ref) li = domEls.tree.querySelector(`li[data-dom-key$="${CSS.escape(node.ref)}"]`);
  if (!li) {
    domEls.tree.querySelectorAll('li[data-dom-key]').forEach(cand => {
      if (!li && cand.querySelector('.tree-label')?.textContent === bestLabel(node)) li = cand;
    });
  }
  if (!li) return;
  // expand all ancestors
  let p = li.parentElement;
  while (p && p !== domEls.tree) {
    if (p.tagName === 'LI' && p.getAttribute('aria-expanded') === 'false')
      p.setAttribute('aria-expanded', 'true');
    p = p.parentElement;
  }
  const row = li.querySelector(':scope > .tree-node-row');
  if (row) { row.classList.add('is-target'); li.setAttribute('aria-current', 'true'); }
  li.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  if (node.x != null) drawBbox(node, true);
}
```

- [ ] **Step 2: Verify target ember + bbox offline**

Set `USE_LIVE_BACKEND = false`. Ensure the demo `fetchTree` tree includes bbox coords (it does from Task 9). Make the demo call `showTreeForStep` with a `targetVal` matching one node's text (e.g. `'Log in'`). Reload, open drawer: the `Log in` row shows the **ember left-rail**, scrolls into view, and an **ember rectangle** appears over that region of the screenshot. Hovering another node shows a **blue** rectangle. **Revert `USE_LIVE_BACKEND = true`.**

- [ ] **Step 3: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): bbox overlay (blue hover / ember target) + target highlight + ancestor auto-expand"
```

---

### Task 12: JS — ARIA keyboard nav + search/filter

**Files:**
- Modify: `playground/index.html`

- [ ] **Step 1: Add keyboard navigation (roving tabindex, arrows, copy)**

Insert after the bbox block:

```js
/* ---- ARIA tree keyboard navigation (roving tabindex) ---- */
function visibleTreeItems() {
  return Array.from(domEls.tree.querySelectorAll('li[role="treeitem"]'))
    .filter(li => li.offsetParent !== null);   // skip collapsed-away
}
function focusItem(li) {
  domEls.tree.querySelectorAll('li[role="treeitem"]').forEach(n => n.tabIndex = -1);
  if (li) { li.tabIndex = 0; li.focus(); }
}
domEls.tree.addEventListener('keydown', e => {
  const items = visibleTreeItems();
  const cur = document.activeElement.closest('li[role="treeitem"]');
  const idx = items.indexOf(cur);
  if (e.key === 'ArrowDown') { e.preventDefault(); focusItem(items[Math.min(idx + 1, items.length - 1)]); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); focusItem(items[Math.max(idx - 1, 0)]); }
  else if (e.key === 'ArrowRight') { e.preventDefault();
    if (cur && cur.getAttribute('aria-expanded') === 'false') cur.setAttribute('aria-expanded', 'true');
    else if (cur && cur.getAttribute('aria-expanded') === 'true') focusItem(items[idx + 1]); }
  else if (e.key === 'ArrowLeft') { e.preventDefault();
    if (cur && cur.getAttribute('aria-expanded') === 'true') cur.setAttribute('aria-expanded', 'false');
    else if (cur) { const parent = cur.parentElement.closest('li[role="treeitem"]'); if (parent) focusItem(parent); } }
  else if (e.key === 'Home') { e.preventDefault(); focusItem(items[0]); }
  else if (e.key === 'End') { e.preventDefault(); focusItem(items[items.length - 1]); }
  else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault();
    const ref = cur && cur.querySelector('.tree-ref'); if (ref) ref.click(); }
  else if (e.key === '/') { e.preventDefault(); domEls.search.focus(); }
});
```

- [ ] **Step 2: Add search/filter**

Insert after the keyboard block:

```js
/* ---- search / filter (hide non-matches; dim ancestors kept for context) ---- */
domEls.search.addEventListener('input', () => {
  const q = domEls.search.value.trim().toLowerCase();
  const items = domEls.tree.querySelectorAll('li[role="treeitem"]');
  if (!q) { items.forEach(li => { li.style.display = ''; clearMark(li); }); return; }
  // first hide all, then reveal matches + their ancestor chain
  items.forEach(li => { li.style.display = 'none'; clearMark(li); });
  items.forEach(li => {
    const row = li.querySelector(':scope > .tree-node-row');
    const txt = (row ? row.textContent : '').toLowerCase();
    if (txt.includes(q)) {
      li.style.display = '';
      markHit(li, q);
      let p = li.parentElement;
      while (p && p !== domEls.tree) {
        if (p.tagName === 'LI') { p.style.display = ''; p.setAttribute('aria-expanded', 'true'); }
        p = p.parentElement;
      }
    }
  });
});
domEls.search.addEventListener('keydown', e => {
  if (e.key === 'Escape') { domEls.search.value = ''; domEls.search.dispatchEvent(new Event('input')); }
});
function markHit(li, q) {
  const lbl = li.querySelector(':scope > .tree-node-row .tree-label');
  if (!lbl) return;
  const t = lbl.textContent; const i = t.toLowerCase().indexOf(q);
  if (i < 0) return;
  lbl.innerHTML = escapeHtml(t.slice(0, i)) + '<span class="tree-mark">' +
    escapeHtml(t.slice(i, i + q.length)) + '</span>' + escapeHtml(t.slice(i + q.length));
}
function clearMark(li) {
  const lbl = li.querySelector(':scope > .tree-node-row .tree-label');
  if (lbl && lbl.querySelector('.tree-mark')) lbl.textContent = lbl.textContent;
}
// diff badge → toggle "changes-only" view
domEls.diff.addEventListener('click', () => {
  domEls.tree.classList.toggle('changes-only');
});
```

Add the changes-only CSS to the CSS block (Task 6):
```css
#treeContainer.changes-only li:not(.dom-node-added):not(:has(.dom-field-changed)) { display: none; }
```

- [ ] **Step 3: Verify keyboard + search offline**

Set `USE_LIVE_BACKEND = false`. Reload, open drawer, click into the tree: ↑/↓ move focus (visible focus ring), →/← expand/collapse, `Enter` copies locator (badge flips to "copied"), `/` jumps to search. Type in search → non-matches hide, matches highlight amber, ancestors stay. `Esc` clears. **Revert `USE_LIVE_BACKEND = true`.**

- [ ] **Step 4: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): DOM tree ARIA keyboard nav + search/filter + changes-only toggle"
```

---

### Task 13: JS — wire into live events (`onStepEvent`/`selectStep`/`resetTimeline`) + mobile degrade

**Files:**
- Modify: `playground/index.html`

- [ ] **Step 1: Light the tab pip + lazy-show on each live step**

In `onStepEvent(ev)` (≈ line 1764), at the end of the function (after `els.srLive.textContent = ...`), add:

```js
  // ⭐ Brain's Eye View: a tree exists for this step → light the tab pip + (if the
  // drawer is open) show/reconcile to this step's tree.
  if (ev.has_dom_tree) {
    domEls.tab.classList.add('has-data');
    showTreeForStep(ev.run_id, ev.step_index, ev.locator_value);
  }
```

- [ ] **Step 2: Tree-follow on step selection (time-travel)**

In `selectStep(stepIndex)` (≈ line 1516), after the screenshot rewind block, add:

```js
  // tree-follow: show the selected step's tree (if the drawer is open)
  if (_currentRunId) showTreeForStep(_currentRunId, stepIndex, step.locator_value);
```

- [ ] **Step 3: Reset tree on new run**

In `resetTimeline()` (≈ line 2801), add:

```js
  domEls.tree.innerHTML = '';
  _treeShownStep = null;
  _treeCache.clear();
  domEls.tab.classList.remove('has-data');
  domEls.diff.hidden = true;
  clearBbox();
```

- [ ] **Step 4: Mobile-degrade verification (and notice)**

The `data-platform` attr (Task 7 Step 3) already drives the amber hover-rail via CSS. `renderTreeFull` already shows the no-bbox notice on non-web. `drawBbox` already no-ops when `state.platform !== 'web'`. Confirm there's nothing else to wire: search the file for any place that assumes `ref`/bbox unconditionally — there should be none (renderer guards `platform === 'web' && node.ref`).

- [ ] **Step 5: Full live verification (real backend, web)**

```bash
# Terminal A
screenforge --playground
# Terminal B (web; opt-in sink)
screenforge --action goto --platform web --extra-value "https://example.com" \
  --session-id domtest --playground-sink --json
screenforge --action assert_exist --platform web --locator-type text \
  --locator-value "Example Domain" --session-id domtest --playground-sink --json
screenforge --action click --platform web --locator-type text \
  --locator-value "More information..." --session-id domtest --playground-sink --json
```
Open `http://127.0.0.1:7860`. Manual checklist:
- Tab pip lights ember after step 1.
- Open drawer (`B`): the filtered hierarchical tree renders; the clicked element shows the **ember rail** + **ember bbox** on the screenshot.
- Time-travel: click filmstrip frame 1 → tree reconciles back to step-1's tree; click frame 3 → forward. Expand/scroll state persists across steps.
- `+N −N ~N` badge updates per step.
- Hover a node → blue bbox aligns with the element on the screenshot.

- [ ] **Step 6: Mobile smoke (if a device is available; else note skipped)**

```bash
screenforge --action click --platform android --locator-type text \
  --locator-value "Settings" --session-id andtest --playground-sink --json
```
Checklist: tree renders **hierarchically** (a real improvement over the flat LLM output); **no `@N` badges**, **no bbox overlay**, **amber** hover rail, one-time no-bbox notice (dismissable, persists). If no device, record "mobile live-smoke skipped (no device)" — do not fake it.

- [ ] **Step 7: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add playground/index.html
git commit -m "feat(playground): wire DOM tree to live steps + time-travel + new-run reset + mobile degrade"
```

---

## Phase 4 — Verification & docs

### Task 14: Full CI reproduction + live-smoke sign-off

**Files:** none (verification only)

- [ ] **Step 1: Ruff (whole repo — the new module must pass)**

Run: `ruff check .`
Expected: `All checks passed!` (exit 0). Fix any E/F/W/I in `dom_capture.py` / edited files. Verify exit code: `ruff check .; echo "exit=$?"`.

- [ ] **Step 2: mypy (CI scope)**

Run: `mypy cli/ common/ config/ utils/`
Expected: no NEW errors vs. baseline. `cli/playground_sink.py` is in scope (lenient); `playground/dom_capture.py` is OUT of scope (playground/ not in the mypy paths). Verify: `mypy cli/ common/ config/ utils/; echo "exit=$?"`.

- [ ] **Step 3: pytest (full suite)**

Run: `pytest tests/ -q`
Expected: all pass (existing 278 + the new dom-capture/app/sink tests; the ~15 live-smoke remain skipped). Verify: `pytest tests/ -q; echo "exit=$?"`.

- [ ] **Step 4: Record the live-smoke result**

Note in the PR/commit body which live-smoke checklists (Task 13 Steps 5–6) passed and whether mobile was exercised or skipped (no device). Honesty over green-washing.

- [ ] **Step 5: Commit (if any lint/type fixes were needed)**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add -A
git commit -m "chore(playground): satisfy ruff/mypy for the DOM tree feature"
```

---

### Task 15: Docs — bilingual capability-matrix + playground-guide + CHANGELOG

**Files:**
- Modify: `docs/capability-matrix.md` + `docs/capability-matrix_CN.md`
- Modify: `docs/playground-guide.md` + `docs/playground-guide_CN.md`
- Modify: `CHANGELOG.md` + `CHANGELOG_CN.md`

> Repo convention: **English is canonical**, `_CN` mirrors it. Keep EN↔CN parity. GitHub anchors change when headings are translated — verify cross-doc links resolve.

- [ ] **Step 1: capability-matrix — add a "Brain's Eye View" subsection under the Playground section**

In `docs/capability-matrix.md`, under `## Playground Live Mirror (2026-06)`, add a blockquote documenting: the sidecar hierarchical capture (does NOT touch the compressors), the `--playground-sink`-gated observer path, disk-backed `run_key`-keyed store, on-demand GET, `has_dom_tree` SSE bool, web ref/bbox vs mobile honest degrade (no ref/bbox, but genuinely hierarchical), read-only. Mirror verbatim-in-Chinese into `docs/capability-matrix_CN.md` under `## Playground 实时镜像台（Live Mirror，2026-06）`. Add to the "已落地/known boundaries" list: "Brain's Eye View DOM tree is single-session, read-only; reverse spatial lookup + SSE diff-stream are deferred."

- [ ] **Step 2: playground-guide — add a "Brain's Eye View" usage section**

In `docs/playground-guide.md`, add a section after "界面功能/UI features": how to open (the `Tree` tab / `B`), what the ember target + bbox mean, hover/keyboard/search/copy, the `+N −N ~N` badge, and the honest mobile degrade. Mirror into `docs/playground-guide_CN.md`.

- [ ] **Step 3: CHANGELOG — add an Unreleased entry (both languages)**

In `CHANGELOG.md` under `## [Unreleased]` (create the section if absent, above the latest released version), add under `### Added`:
```markdown
- **Playground "Brain's Eye View" DOM tree** — a read-only, live, hierarchical view of the AI brain's filtered element set, re-hung into its real parent/child structure. Captured via a sidecar that never touches the LLM-facing compressors; gated by `--playground-sink` (off by default = zero cost); pushed fire-and-forget and stored on disk keyed by the playground run key; fetched on demand (zero SSE tree overhead). The current target element is ember-lit and (on web) cross-linked to a bbox overlay on the screenshot. Honest mobile degrade (no ref/bbox; still genuinely hierarchical). Drawer toggle: `B`.
```
Mirror into `CHANGELOG_CN.md` under `## [未发布]` / `### 新增`.

- [ ] **Step 4: Verify internal links resolve**

Run a quick anchor check (the repo's prior pattern): confirm any new cross-doc links (e.g. capability-matrix ↔ playground-guide) resolve under GitHub's heading-anchor algorithm (lowercase, strip punctuation, spaces→hyphens, CJK kept). Spot-check by grepping the link targets exist as headings:
```bash
grep -n "Brain's Eye View\|Brain’s Eye View" docs/capability-matrix.md docs/playground-guide.md
```

- [ ] **Step 5: Commit**

```bash
git checkout -- AGENTS.md 2>/dev/null || true
git add docs/capability-matrix.md docs/capability-matrix_CN.md docs/playground-guide.md docs/playground-guide_CN.md CHANGELOG.md CHANGELOG_CN.md
git commit -m "docs(playground): document Brain's Eye View DOM tree (bilingual: matrix + guide + changelog)"
```

---

## Self-Review (completed by plan author)

**1. Spec coverage** — every spec section maps to a task:
- §2.1 capture module → Tasks 1–2 (`dom_capture.py` mobile + web).
- §2.2 hook point & red line (gated, fire-and-forget, no-join tree push) → Task 3.
- §2.3 corrected store (server-owned, run_key-keyed, disk, LRU≤5, `has_dom_tree`, GET) → Tasks 4–5.
- §3 UX shape (drawer/pin, ember target, hover bbox, read-only) → Tasks 6–13.
- §4 keyed reconciler (web `@N` / mobile djb2, patch-in-place, animations, diff badge) → Tasks 9–10.
- §5 scale/perf (collapse defaults, depth handling, no virtualization) → Tasks 9–10 (collapse defaults in `createTreeLi`; no virtualization is the explicit v1 choice).
- §6 honest boundaries + mobile degrade → Tasks 11/13 (no-op bbox, amber rail, notice) + Task 15 docs.

**2. Placeholder scan** — no TBD/TODO-as-work; the only `// TODO: reverse-spatial-lookup` is an intentional deferred-marker per the spec. All code steps contain complete code.

**3. Type/name consistency** — verified across tasks: `build_mobile_tree(raw_xml, platform)`, `build_web_tree(page)`, `PlaygroundSink.capture_dom_tree`, `push_dom_tree`/`_post_dom`, `has_dom_tree`, `_DOM_DIR`/`_dom_index`/`_MAX_DOM_RUNS`/`_dom_run_dir`/`_dom_evict_if_needed`, `POST /api/dom`, `GET /api/run/{run_id}/step/{step_index}/dom`; JS: `domEls`, `showTreeForStep`, `fetchTree`, `renderTreeFull`, `reconcileTree`, `createTreeLi`, `childKey`/`djb2`, `patchNodeLi`/`syncFlag`/`_ensureChildUl`, `drawBbox`/`clearBbox`/`highlightTarget`/`findNodeByTarget`, `onDrawerOpened`, `_treeCache`/`_treeShownStep`. Names are consistent between definition and use.

**4. Known honest caveats baked into the plan** — (a) the web tree's `@N` is the tree-builder's own ordinal, best-effort aligned with the compressor's but not guaranteed identical (the authoritative locator is the code panel); (b) the v1 reconciler adds/patches/removes but does not fully reorder siblings (correct for stable in-page structure; full-nav falls back to clean render); (c) iOS tree reuses Android predicates against WDA XML — best-effort, degrades to fewer nodes rather than crashing; (d) frontend has no JS unit harness — verified via the offline demo feed + manual checklist, matching the repo's existing practice.

---

## Execution Handoff

See the offer after this document.
