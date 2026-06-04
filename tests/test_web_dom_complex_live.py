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


# --- regression: simple pages still work -----------------------------------

def test_plain_page_unchanged(page):
    """The pierce/iframe rewrite must not regress the ordinary light-DOM case."""
    els = _compress(page, "<h1>Title</h1><button id='go'>Go</button><input name='q'>")
    txts = _texts(els)
    assert "Go" in txts
    assert any(e.get("name") == "q" for e in els)
    assert any(e.get("id") == "go" and e.get("clickable") for e in els)
