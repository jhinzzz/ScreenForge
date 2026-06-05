"""Live web tests for compress_web_dom against COMPLEX, real-world DOM shapes.

WHY THIS EXISTS: the original live smoke used tiny `data:` pages, which masked
real defects in the DOM compressor — the LLM's "eyes". Probing a complex page
(shadow DOM, iframes, disabled controls, duplicate-text elements) surfaced four
blind spots:
  1. open shadow DOM content was invisible (Playwright could click it, but the
     compressor never reported it → the LLM could never target it);
  2. nested shadow DOM likewise invisible;
  3. same-origin / srcdoc iframe content invisible;
  4. disabled / aria-disabled buttons were reported clickable=True (the LLM would
     try to click them and hang on the timeout).

These tests pin the corrected contract against a real Chromium. They are the
regression net for the compressor — the single most important capability in the
product, since every located action depends on it.

OPT-IN: RUN_LIVE_WEB_SMOKE=1 pytest tests/test_web_dom_complex_live.py -v
Self-skips when Chromium isn't installed.
"""

import json
import os
from urllib.parse import quote as _quote

import pytest

_RUN = os.getenv("RUN_LIVE_WEB_SMOKE", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live_web,
    pytest.mark.skipif(
        not _RUN,
        reason="Live web smoke is opt-in. Set RUN_LIVE_WEB_SMOKE=1 (needs real Chromium).",
    ),
]


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        pw = sync_playwright().start()
        path = pw.chromium.executable_path
        pw.stop()
        return bool(path) and os.path.exists(path)
    except Exception:
        return False


@pytest.fixture
def page():
    """A bare real Chromium page (no persistent-session machinery needed here —
    we only exercise compress_web_dom against static complex DOM)."""
    if not _chromium_available():
        pytest.skip("Playwright/Chromium not installed")
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch()
    pg = browser.new_page()
    try:
        yield pg
    finally:
        browser.close()
        pw.stop()


def _compress(pg, html: str) -> list:
    from utils.utils_web import compress_web_dom

    pg.goto("data:text/html," + _quote(html))
    pg.wait_for_timeout(200)
    return json.loads(compress_web_dom(pg)).get("ui_elements", [])


def _texts(els) -> set:
    return {(e.get("text") or "").strip() for e in els}


# --- Shadow DOM ------------------------------------------------------------

_OPEN_SHADOW = (
    "<button>LightButton</button>"
    "<div id='host'></div>"
    "<script>"
    "document.getElementById('host').attachShadow({mode:'open'})"
    ".innerHTML=\"<button>OpenShadowBtn</button>\";"
    "</script>"
)

_NESTED_SHADOW = (
    "<div id='host'></div>"
    "<script>"
    "var n=document.getElementById('host').attachShadow({mode:'open'});"
    "var inner=document.createElement('div'); n.appendChild(inner);"
    "inner.attachShadow({mode:'open'}).innerHTML=\"<button>NestedShadowBtn</button>\";"
    "</script>"
)


def test_open_shadow_dom_is_visible(page):
    els = _compress(page, _OPEN_SHADOW)
    txts = _texts(els)
    assert "LightButton" in txts, "regression: light-DOM button lost"
    assert "OpenShadowBtn" in txts, (
        "compressor is blind to open shadow DOM — the LLM can never target it"
    )


def test_nested_shadow_dom_is_visible(page):
    els = _compress(page, _NESTED_SHADOW)
    assert "NestedShadowBtn" in _texts(els), "compressor doesn't recurse into nested shadow roots"


# --- iframe ---------------------------------------------------------------

_SRCDOC_IFRAME = (
    "<button>OuterBtn</button>"
    "<iframe srcdoc=\"<button>IframeBtn</button>\"></iframe>"
)


def test_same_origin_iframe_is_visible(page):
    els = _compress(page, _SRCDOC_IFRAME)
    txts = _texts(els)
    assert "OuterBtn" in txts, "regression: top-document button lost"
    assert "IframeBtn" in txts, "compressor doesn't descend into same-origin/srcdoc iframes"


def test_iframe_element_coordinates_match_playwright_truth(page):
    """An iframe child's bbox must be in TOP-document coordinates within ~1px of
    Playwright's own measurement — including the iframe's border+padding inset,
    not just its border-box origin. A few-px drift would mis-click bordered
    embed/payment frames (the exact timeout this whole change set removes)."""
    html = (
        "<div style='height:120px'>spacer</div>"
        "<iframe style='width:300px;height:200px;border:20px solid #000;padding:10px' "
        "srcdoc=\"<button id='b'>IframeBtn</button>\"></iframe>"
    )
    page.goto("data:text/html," + _quote(html))
    page.wait_for_timeout(200)
    from utils.utils_web import compress_web_dom

    els = json.loads(compress_web_dom(page)).get("ui_elements", [])
    btn = next((e for e in els if (e.get("text") or "") == "IframeBtn"), None)
    assert btn is not None, "iframe button not captured"
    # Ground truth: Playwright's own bounding_box for the same element.
    truth = page.frame_locator("iframe").locator("#b").bounding_box()
    assert abs(btn["x"] - truth["x"]) <= 2, f"x off: compressor {btn['x']} vs truth {truth['x']}"
    assert abs(btn["y"] - truth["y"]) <= 2, f"y off: compressor {btn['y']} vs truth {truth['y']}"


def test_interactive_shadow_host_with_light_text_visible(page):
    """A clickable custom-element host whose light text isn't slotted has
    innerText=='' — it must still be captured (via directText), or the LLM stays
    blind to a clickable element (the blind spot this change targets)."""
    html = (
        "<div id='host' onclick='void 0' style='cursor:pointer'>HostLightText</div>"
        "<script>"
        "document.getElementById('host').attachShadow({mode:'open'})"
        ".innerHTML=\"<button>InnerShadowBtn</button>\";"
        "</script>"
    )
    els = _compress(page, html)
    txts = _texts(els)
    assert "InnerShadowBtn" in txts, "shadow child lost"
    assert "HostLightText" in txts, (
        "clickable shadow host with light text dropped — LLM can't see/target it"
    )


# --- disabled controls -----------------------------------------------------

_DISABLED = (
    "<button disabled>NativeDisabled</button>"
    "<button aria-disabled='true'>AriaDisabled</button>"
    "<button>EnabledBtn</button>"
)


def test_native_disabled_button_not_clickable(page):
    els = _compress(page, _DISABLED)
    nd = next((e for e in els if (e.get("text") or "") == "NativeDisabled"), None)
    assert nd is not None, "disabled button should still be reported (for assertions)"
    assert nd.get("clickable") is False, (
        "native-disabled button marked clickable — the LLM will click it and hang"
    )


def test_aria_disabled_button_not_clickable(page):
    els = _compress(page, _DISABLED)
    ad = next((e for e in els if (e.get("text") or "") == "AriaDisabled"), None)
    assert ad is not None
    assert ad.get("clickable") is False, "aria-disabled button marked clickable"


def test_enabled_button_still_clickable(page):
    """Guard against over-correction: a normal button stays clickable."""
    els = _compress(page, _DISABLED)
    eb = next((e for e in els if (e.get("text") or "") == "EnabledBtn"), None)
    assert eb is not None and eb.get("clickable") is True


# --- disabled <fieldset> propagation ---------------------------------------

_FIELDSET_DISABLED = (
    "<fieldset disabled>"
    "<legend>Section</legend>"
    "<button>InsideDisabledFieldset</button>"
    "<input name='fld_input'>"
    "</fieldset>"
    "<button>OutsideBtn</button>"
)


def test_disabled_fieldset_propagates_to_child_controls(page):
    """HTML spec: a <fieldset disabled> disables ALL descendant form controls,
    not just controls carrying their own `disabled` attribute. The compressor
    only checked el.disabled (the element's OWN attribute), so a button/input
    inside a disabled fieldset was reported clickable=True — the LLM would click
    it and hang on the timeout (same failure class as the native-disabled fix)."""
    els = _compress(page, _FIELDSET_DISABLED)
    btn = next((e for e in els if (e.get("text") or "") == "InsideDisabledFieldset"), None)
    assert btn is not None, "control inside disabled fieldset should still be reported"
    assert btn.get("clickable") is False, (
        "button inside <fieldset disabled> reported clickable — fieldset disabling "
        "not propagated; the LLM will click it and hang"
    )
    inp = next((e for e in els if e.get("name") == "fld_input"), None)
    assert inp is not None, "input inside disabled fieldset should still be reported"
    assert inp.get("clickable") is False, "input inside <fieldset disabled> reported clickable"
    # The unrelated outside button must stay clickable (no over-correction).
    out = next((e for e in els if (e.get("text") or "") == "OutsideBtn"), None)
    assert out is not None and out.get("clickable") is True


_FIELDSET_DISABLED_LEGEND = (
    "<fieldset disabled>"
    "<legend><button>LegendBtn</button></legend>"
    "<button>BodyBtn</button>"
    "</fieldset>"
)


def test_disabled_fieldset_legend_child_remains_clickable(page):
    """Spec exception: controls inside the FIRST <legend> of a disabled fieldset
    are NOT disabled (e.g. a collapse/expand toggle in the legend). Guards against
    an over-broad fix that disables the whole subtree."""
    els = _compress(page, _FIELDSET_DISABLED_LEGEND)
    legend_btn = next((e for e in els if (e.get("text") or "") == "LegendBtn"), None)
    body_btn = next((e for e in els if (e.get("text") or "") == "BodyBtn"), None)
    assert legend_btn is not None and legend_btn.get("clickable") is True, (
        "legend child of disabled fieldset wrongly disabled — over-correction"
    )
    assert body_btn is not None and body_btn.get("clickable") is False, (
        "non-legend child of disabled fieldset still reported clickable"
    )


_FIELDSET_NESTED = (
    "<fieldset disabled>"  # outer
    "<legend>Outer</legend>"
    "<fieldset disabled>"  # inner
    "<legend><button>InnerLegendBtn</button></legend>"
    "<button>DeepBodyBtn</button>"
    "</fieldset>"
    "</fieldset>"
)


def test_nested_disabled_fieldset_legend_still_disabled_by_outer(page):
    """The legend-exemption is per-fieldset, not absolute. A control in the INNER
    fieldset's legend is exempt from the inner fieldset, but it sits in the OUTER
    disabled fieldset's BODY, so the outer fieldset still disables it (HTML spec).
    A naive single-`closest('fieldset[disabled]')` fix gets this wrong (reports it
    clickable); the implementation must consider every ancestor disabled fieldset."""
    els = _compress(page, _FIELDSET_NESTED)
    legend_btn = next((e for e in els if (e.get("text") or "") == "InnerLegendBtn"), None)
    assert legend_btn is not None, "inner-legend button should still be reported"
    assert legend_btn.get("clickable") is False, (
        "inner-legend button reported clickable — outer disabled fieldset's "
        "propagation was missed (naive single-closest fix)"
    )


_FIELDSET_REENABLE = (
    "<fieldset disabled>"  # outer disabled
    "<legend>Outer</legend>"
    "<fieldset>"  # inner NOT disabled — must NOT re-enable
    "<button>InnerNonDisabledBtn</button>"
    "</fieldset>"
    "</fieldset>"
)


def test_nested_non_disabled_fieldset_does_not_reenable(page):
    """A non-disabled inner <fieldset> does NOT re-enable controls that an outer
    <fieldset disabled> disabled (HTML spec: disabling propagates down; only the
    fieldset's own first <legend> is exempt, never a nested plain fieldset). A
    reader might naively expect the inner fieldset to "reset" the state — it does
    not, and :disabled gets this right."""
    els = _compress(page, _FIELDSET_REENABLE)
    btn = next((e for e in els if (e.get("text") or "") == "InnerNonDisabledBtn"), None)
    assert btn is not None, "button in nested non-disabled fieldset should still be reported"
    assert btn.get("clickable") is False, (
        "nested non-disabled fieldset wrongly re-enabled a control the outer "
        "disabled fieldset disabled"
    )


# --- inert subtree (modal backdrop pattern) --------------------------------

_INERT = (
    "<div inert>"
    "<button>InertBackgroundBtn</button>"
    "<input name='inert_input'>"
    "</div>"
    "<div role='dialog'><button>ModalOkBtn</button></div>"
)


def test_inert_subtree_controls_not_clickable(page):
    """The `inert` attribute (the standard modal-backdrop pattern: everything
    behind an open <dialog> is marked inert) makes a subtree non-interactive —
    the browser swallows clicks on it. Such controls are still visible (bbox > 0)
    so the compressor emits them, but with clickable=True the LLM targets a dead
    button behind the modal and the click no-ops/hangs — the same failure class as
    disabled controls. `:disabled` does NOT catch inert; must check closest('[inert]')."""
    els = _compress(page, _INERT)
    bg = next((e for e in els if (e.get("text") or "") == "InertBackgroundBtn"), None)
    assert bg is not None, "inert button should still be reported (for assertions)"
    assert bg.get("clickable") is False, (
        "button inside an inert subtree reported clickable — the LLM will target a "
        "dead control behind the modal; inert not honored"
    )
    # Honesty: inert is NOT disabled. Surface it as its own signal so an
    # `assert disabled` can't wrongly pass and the LLM can reason "a modal is
    # open" (dismiss it) rather than "the form is disabled".
    assert bg.get("inert") is True, "inert control should carry an explicit inert flag"
    assert bg.get("disabled") is not True, (
        "inert wrongly conflated with disabled — they are distinct DOM concepts"
    )
    inp = next((e for e in els if e.get("name") == "inert_input"), None)
    assert inp is not None and inp.get("clickable") is False, "inert input reported clickable"
    # The active modal button (outside the inert subtree) must stay clickable.
    ok = next((e for e in els if (e.get("text") or "") == "ModalOkBtn"), None)
    assert ok is not None and ok.get("clickable") is True, (
        "active modal button wrongly marked non-clickable — over-correction"
    )


_INERT_SHADOW = (
    "<div inert><div id='ihost'></div></div>"
    "<script>"
    "document.getElementById('ihost').attachShadow({mode:'open'})"
    ".innerHTML=\"<button>ShadowInertBtn</button>\";"
    "</script>"
)


def test_inert_pierces_shadow_boundary(page):
    """A shadow-DOM component whose HOST sits behind an inert backdrop is
    click-blocked by the browser, but el.closest('[inert]') from inside the shadow
    tree returns null (closest stops at the shadow root). The walk must therefore
    INHERIT the host's inert state across the boundary — exactly as it already
    inherits coordinate offsets — or the LLM targets a dead shadow control and
    hangs (the same failure class, leaking through the shadow boundary)."""
    els = _compress(page, _INERT_SHADOW)
    btn = next((e for e in els if (e.get("text") or "") == "ShadowInertBtn"), None)
    assert btn is not None, "shadow button behind inert backdrop should still be reported"
    assert btn.get("clickable") is False, (
        "shadow control behind an inert backdrop reported clickable — inert not "
        "inherited across the shadow boundary"
    )


_INERT_IFRAME = (
    "<div inert>"
    "<iframe srcdoc=\"<button>IframeInertBtn</button>\"></iframe>"
    "</div>"
)


def test_inert_pierces_iframe_boundary(page):
    """Same boundary gap for same-origin iframes: content inside an iframe that
    sits in an inert subtree is click-blocked, but closest('[inert]') inside the
    frame document can't see the parent's inert ancestor. The walk must inherit
    inert when descending into the frame."""
    els = _compress(page, _INERT_IFRAME)
    btn = next((e for e in els if (e.get("text") or "") == "IframeInertBtn"), None)
    assert btn is not None, "iframe button behind inert backdrop should still be reported"
    assert btn.get("clickable") is False, (
        "iframe control behind an inert backdrop reported clickable — inert not "
        "inherited when descending into the frame document"
    )


_FREE_SHADOW = (
    "<div id='fhost'></div>"
    "<script>"
    "document.getElementById('fhost').attachShadow({mode:'open'})"
    ".innerHTML=\"<button>FreeShadowBtn</button>\";"
    "</script>"
)


def test_shadow_without_inert_stays_clickable(page):
    """Over-correction guard for the cross-boundary direction: a shadow control
    with NO inert anywhere must stay clickable. Pins that inheritedInert defaults
    to false and isn't accidentally "sticky" across the shadow boundary."""
    els = _compress(page, _FREE_SHADOW)
    btn = next((e for e in els if (e.get("text") or "") == "FreeShadowBtn"), None)
    assert btn is not None, "free shadow button must be captured (no inert)"
    assert btn.get("clickable") is True, (
        "shadow control with no inert wrongly marked non-clickable — inert state "
        "leaked across the boundary as sticky"
    )
    assert btn.get("inert") is not True, "non-inert element should not carry inert flag"


_COMPOSITE_INERT = (
    "<div inert>"
    "<iframe srcdoc=\""
    "<div id='ch'></div>"
    "<scr" "ipt>"
    "document.getElementById('ch').attachShadow({mode:'open'})"
    ".innerHTML='<button>DeepDeepBtn</button>';"
    "</scr" "ipt>\"></iframe>"
    "</div>"
)


def test_inert_inherits_across_stacked_boundaries(page):
    """Composite: a shadow component INSIDE an iframe INSIDE an inert subtree —
    two stacked boundaries. Inert must compose across both (iframe→frameInert, then
    shadow→isInertEl(host, inheritedInert)), or a deeply-nested shadow control behind
    a modal is reported clickable. Pins inheritance COMPOSITION, which single-boundary
    tests can't catch."""
    els = _compress(page, _COMPOSITE_INERT)
    btn = next((e for e in els if (e.get("text") or "") == "DeepDeepBtn"), None)
    assert btn is not None, "shadow-in-iframe button should still be reported"
    assert btn.get("clickable") is False, (
        "shadow-in-iframe control behind inert reported clickable — inert did not "
        "compose across the stacked iframe+shadow boundaries"
    )


# --- virtual scrolling (react-window style) --------------------------------

# 1000 logical rows, but only ~8 are ever in the DOM at once: a scroll handler
# re-renders the visible slice based on scrollTop (the react-window pattern).
_VIRTUAL_LIST = (
    "<div id='vp' style='height:160px;overflow:auto'>"
    "<div id='spacer' style='height:20000px;position:relative'>"
    "<div id='win'></div>"
    "</div></div>"
    "<script>"
    "var vp=document.getElementById('vp'),win=document.getElementById('win');"
    "function render(){var top=vp.scrollTop,first=Math.floor(top/20),h='';"
    "for(var i=first;i<first+8;i++){h+=\"<button style='position:absolute;top:\"+(i*20)+\"px;height:20px'>Row\"+i+\"</button>\";}"
    "win.innerHTML=h;}"
    "vp.addEventListener('scroll',render);render();"
    "</script>"
)


def _row_nums(els) -> list:
    out = []
    for e in els:
        t = (e.get("text") or "")
        if t.startswith("Row"):
            out.append(int(t[3:]))
    return sorted(out)


def test_virtual_list_shows_only_viewport_then_new_rows_after_scroll(page):
    """Virtual lists (react-window/virtualized tables) only render the rows in the
    viewport — off-screen rows do NOT exist in the DOM, so the compressor cannot
    and should not report them. This pins the HONEST contract: (1) initially only
    the viewport slice is visible; (2) after scroll + re-inspect, the NEW slice is
    visible. The workflow-B pattern (action scroll -> re-inspect) is therefore the
    correct way to reach more rows. A regression here would mean either blindness
    (re-inspect misses new rows) or a token blowup (forcing all 1000 rows into the
    tree). Both are failures."""
    page.goto("data:text/html," + _quote(_VIRTUAL_LIST))
    page.wait_for_timeout(200)
    from utils.utils_web import compress_web_dom

    initial = _row_nums(json.loads(compress_web_dom(page)).get("ui_elements", []))
    assert initial, "no rows captured at all — compressor blind to the rendered slice"
    assert initial[0] == 0, f"viewport should start at Row0, got {initial[:3]}"
    assert len(initial) < 50, (
        f"virtual list leaked {len(initial)} rows into the tree — only the viewport "
        "slice should be reported (token blowup otherwise)"
    )
    assert 200 not in initial, "Row200 is off-screen initially; must not be reported"

    # Scroll the viewport and re-inspect — the standard workflow-B loop.
    page.evaluate("document.getElementById('vp').scrollTop=4000")
    page.wait_for_timeout(200)
    after = _row_nums(json.loads(compress_web_dom(page)).get("ui_elements", []))
    assert 200 in after, (
        "re-inspect after scroll did NOT pick up the new viewport slice (Row200) — "
        "virtual-list rows are unreachable, breaking the scroll->re-inspect workflow"
    )
    assert 0 not in after, "Row0 scrolled out of view but is still reported (stale)"


# --- duplicate-named controls: scope disambiguation ------------------------

# Each row has a distinguishing label + an IDENTICAL "Delete" button. The label
# is a sibling of the button inside the row <li>, not an ancestor with its own
# text — the realistic shape (and the one a naive ancestor-only rule misses).
_DUPLICATE_ROWS = (
    "<ul>"
    "<li><span>Alice Smith</span><button>Delete</button></li>"
    "<li><span>Bob Jones</span><button>Delete</button></li>"
    "<li><span>Carol White</span><button>Delete</button></li>"
    "</ul>"
)


def test_duplicate_named_buttons_get_scope(page):
    """N identical-named controls (one 'Delete' per row) must each be flagged with
    `scope` = their row's identifying text, so the LLM/codegen can target the right
    one with a stable scoped locator instead of get_by_text('Delete').first (which
    always hits row 1 — the persisted-test lie)."""
    els = _compress(page, _DUPLICATE_ROWS)
    deletes = [e for e in els if (e.get("text") or "") == "Delete"]
    assert len(deletes) == 3, f"expected 3 Delete buttons, got {len(deletes)}"
    scopes = [d.get("scope") for d in deletes]
    assert all(s for s in scopes), (
        f"ambiguous Delete buttons missing scope — cannot disambiguate: {scopes}"
    )
    assert set(scopes) == {"Alice Smith", "Bob Jones", "Carol White"}, (
        f"scope should be each row's label, got {scopes}"
    )
    # dup_index distinguishes them in DOM order even if two rows shared a label.
    idxs = sorted(d.get("dup_index") for d in deletes)
    assert idxs == [0, 1, 2], f"dup_index should be 0,1,2 in DOM order, got {idxs}"


_UNIQUE_BUTTON = "<div><span>Heading</span><button>Delete</button></div>"


def test_non_ambiguous_button_has_no_scope(page):
    """A control whose accessible name is unique on the page must NOT carry
    scope/dup_index — emitting them on every element would bloat tokens (the
    field is only worth its cost when there's a genuine collision)."""
    els = _compress(page, _UNIQUE_BUTTON)
    btn = next((e for e in els if (e.get("text") or "") == "Delete"), None)
    assert btn is not None
    assert btn.get("scope") is None, "scope emitted for a non-ambiguous element (token bloat)"
    assert btn.get("dup_index") is None, "dup_index emitted for a non-ambiguous element"


def test_scoped_locator_resolves_to_the_right_row_live(page):
    """End-to-end proof against real Chromium: the scoped locator the compressor +
    codegen produce for Bob's 'Delete' must resolve to BOB's button — not row 1.
    This is the whole point: a stable locator that hits the intended row. We tag
    each button so we can prove which one the locator selects."""
    html = (
        "<ul>"
        "<li><span>Alice Smith</span><button data-row='alice'>Delete</button></li>"
        "<li><span>Bob Jones</span><button data-row='bob'>Delete</button></li>"
        "<li><span>Carol White</span><button data-row='carol'>Delete</button></li>"
        "</ul>"
    )
    page.goto("data:text/html," + _quote(html))
    page.wait_for_timeout(200)
    from utils.utils_web import compress_web_dom
    from common.executor import build_fallback_locator, get_fallback_element

    els = json.loads(compress_web_dom(page)).get("ui_elements", [])
    bob = next(
        (e for e in els if (e.get("text") or "") == "Delete" and e.get("scope") == "Bob Jones"),
        None,
    )
    assert bob is not None, "compressor didn't scope Bob's Delete button"

    # The emitted persisted locator must be scoped (no .first row-1 lie).
    frag = build_fallback_locator(bob)
    assert frag is not None and ".first" not in frag and "Bob Jones" in frag

    # The LIVE handle (lockstep twin) must resolve to exactly one element — Bob's.
    handle = get_fallback_element(page, bob)
    assert handle is not None
    assert handle.count() == 1, (
        f"scoped locator resolved to {handle.count()} elements — not uniquely Bob's row"
    )
    assert handle.get_attribute("data-row") == "bob", (
        "scoped locator selected the wrong row — disambiguation failed"
    )


def test_substring_row_label_still_disambiguates(page):
    """Adversarial: one row's label is a SUBSTRING of another's ("Bob" vs
    "Bob Jones"). Playwright get_by_text defaults to SUBSTRING matching, so a
    naive get_by_text('Bob') would also match "Bob Jones" → strict-mode ambiguity.
    The scoped locator must use exact matching so "Bob" resolves to ONLY Bob's
    row. This is the realistic shape ("Item"/"Item 2", "Jon"/"Jonathan")."""
    html = (
        "<ul>"
        "<li><span>Bob</span><button data-row='bob'>Delete</button></li>"
        "<li><span>Bob Jones</span><button data-row='bobjones'>Delete</button></li>"
        "</ul>"
    )
    page.goto("data:text/html," + _quote(html))
    page.wait_for_timeout(200)
    from utils.utils_web import compress_web_dom
    from common.executor import get_fallback_element

    els = json.loads(compress_web_dom(page)).get("ui_elements", [])
    bob = next((e for e in els if (e.get("text") or "") == "Delete" and e.get("scope") == "Bob"), None)
    assert bob is not None, "Bob's Delete didn't get scope 'Bob'"
    handle = get_fallback_element(page, bob)
    assert handle is not None and handle.count() == 1, (
        f"scope 'Bob' resolved to {handle.count() if handle else 0} elements — substring "
        "matched 'Bob Jones' too (needs exact match)"
    )
    assert handle.get_attribute("data-row") == "bob"


def test_identical_row_labels_demote_to_skip(page):
    """When two rows share an IDENTICAL label, text-scope cannot disambiguate them.
    The compressor must NOT emit a scope that resolves to >1 element (a persisted
    guaranteed-red locator) — it must demote to the honest unscopable path (no
    scope → build_fallback_locator returns None → pytest.skip)."""
    html = (
        "<ul>"
        "<li><span>Item</span><button>Delete</button></li>"
        "<li><span>Item</span><button>Delete</button></li>"
        "</ul>"
    )
    page.goto("data:text/html," + _quote(html))
    page.wait_for_timeout(200)
    from utils.utils_web import compress_web_dom
    from common.executor import build_fallback_locator

    els = json.loads(compress_web_dom(page)).get("ui_elements", [])
    deletes = [e for e in els if (e.get("text") or "") == "Delete"]
    assert len(deletes) == 2
    for d in deletes:
        assert d.get("scope") in (None, ""), (
            f"identical-label row got non-unique scope {d.get('scope')!r} — would persist "
            "a guaranteed-red locator instead of an honest skip"
        )
        # dup_index still present (it WAS a collision); locator must be None → skip.
        assert d.get("dup_index") is not None
        assert build_fallback_locator(d) is None, "unscopable duplicate must yield None (skip)"


def test_input_submit_grouped_with_button(page):
    """Role-grouping must mirror codegen's _infer_web_role: an <input type=submit>
    and a <button> with the same name BOTH render as get_by_role('button',
    name=...), so they collide and must be detected as ambiguous. A tag-only key
    (input→textbox, button→button) would miss this → the silent .first lie
    survives for mixed control types."""
    html = (
        "<ul>"
        "<li><span>Row A</span><input type='submit' value='Apply'></li>"
        "<li><span>Row B</span><button>Apply</button></li>"
        "</ul>"
    )
    page.goto("data:text/html," + _quote(html))
    page.wait_for_timeout(200)
    from utils.utils_web import compress_web_dom

    els = json.loads(compress_web_dom(page)).get("ui_elements", [])
    applies = [e for e in els if (e.get("text") or "") == "Apply" or e.get("desc") == "Apply"]
    # Both the input[type=submit] and the button carry name "Apply" → 2 controls.
    assert len(applies) >= 2, f"expected the submit input + button, got {applies}"
    assert all(a.get("dup_index") is not None for a in applies), (
        "input[type=submit] and button with same name not detected as a collision — "
        "grouping key diverges from _infer_web_role"
    )


def test_overlong_row_label_not_used_as_scope(page):
    """A scope must be exact-matchable. A leaf label >80 chars cannot be (we'd have
    to truncate, and exact=True would then never match the full node). Such a row
    must NOT get a scope — it routes to the honest skip path instead of persisting
    a fragile/guaranteed-fail locator."""
    long_label = "L" + "o" * 120 + "ng"  # >80 chars, unique per row via suffix
    html = (
        "<ul>"
        f"<li><span>{long_label}A</span><button>Delete</button></li>"
        f"<li><span>{long_label}B</span><button>Delete</button></li>"
        "</ul>"
    )
    page.goto("data:text/html," + _quote(html))
    page.wait_for_timeout(200)
    from utils.utils_web import compress_web_dom
    from common.executor import build_fallback_locator

    els = json.loads(compress_web_dom(page)).get("ui_elements", [])
    deletes = [e for e in els if (e.get("text") or "") == "Delete"]
    assert len(deletes) == 2
    for d in deletes:
        assert not d.get("scope"), f"over-long label used as scope (will fail exact match): {d.get('scope')!r}"
        assert build_fallback_locator(d) is None, "must route to skip, not a truncated-scope locator"


# --- regression: simple pages still work -----------------------------------

def test_plain_page_unchanged(page):
    """The pierce/iframe rewrite must not regress the ordinary light-DOM case."""
    els = _compress(page, "<h1>Title</h1><button id='go'>Go</button><input name='q'>")
    txts = _texts(els)
    assert "Go" in txts
    assert any(e.get("name") == "q" for e in els)
    assert any(e.get("id") == "go" and e.get("clickable") for e in els)


# --- did-you-mean (failure-feedback ergonomics) ---------------------------


def test_did_you_mean_offers_close_match_on_typo(page):
    """A typo'd locator on a real compressed page returns the intended target
    as a candidate, so the driving agent recovers without a blind re-inspect.
    Real DOM + real compression + real difflib ranking — the live value-add
    over the pure-unit diagnoser tests.
    """
    from common.failure_diagnosis import diagnose

    els = _compress(page, "<button id='signin'>Log in</button><button>Cancel</button>")
    diag = diagnose(error_code="E037", locator_value="Logni", ui_elements=els)

    assert diag.candidates, "expected a did-you-mean candidate for the typo 'Logni'"
    assert any("Log in" in c.text for c in diag.candidates), (
        "diagnoser should surface 'Log in' as the close match"
    )
    # The suggested locator should be a web ref the agent can retry with.
    assert diag.candidates[0].locator["type"] == "ref"
