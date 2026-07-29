"""Live layout regression tests for playground/index.html against a real Chromium.

WHY THIS EXISTS: an earlier hand-rolled verification sweep covered viewport
(900, 760) and reported "ALL CLEAN", while a 119px page-level horizontal overflow
existed at exactly that width. The sweep measured overflowing child scrollers,
clipped marks, element overlap and a few text-collapse cases — but never
`documentElement.scrollWidth - clientWidth`. A harness that does not measure a
property cannot fail on it.

The bug it missed: `header` had `flex-wrap: nowrap` with wrap enabled only at
`@media (max-width: 720px)`, so the page scrolled sideways from 721px up to the
header's intrinsic width. That width is content-dependent (~1019px idle, ~1330px
once a run id, a generated filename and a detected editor are present), which is
why the fix is intrinsic-width wrapping rather than a different magic breakpoint —
and why these tests assert against both the idle and the populated bar.

Only DOM geometry is asserted, never pixel colour or exact row counts: those are
font- and platform-dependent and would make this flaky for no gain.

OPT-IN: RUN_LIVE_WEB_SMOKE=1 pytest tests/test_playground_layout_live.py -v
Self-skips when Chromium isn't installed.
"""

import os
from pathlib import Path

import pytest

_RUN = os.getenv("RUN_LIVE_WEB_SMOKE", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live_web,
    pytest.mark.skipif(
        not _RUN,
        reason="Live layout smoke is opt-in. Set RUN_LIVE_WEB_SMOKE=1 (needs real Chromium).",
    ),
]

_INDEX = Path(__file__).resolve().parent.parent / "playground" / "index.html"

# Spans the real breakpoints (1360 / 1080 / 720) plus the band the missed bug lived
# in (721-1330) and the common laptop/tablet/phone widths.
WIDTHS = (
    1920, 1600, 1512, 1440, 1400, 1366, 1360, 1330, 1300, 1280, 1200,
    1100, 1080, 1024, 1019, 960, 900, 800, 768, 721, 720, 600, 480, 375, 320,
)

# The header's widest realistic content: a run id, a generated test filename and a
# detected editor. Idle placeholders are em-dashes, so idle alone under-measures.
_POPULATE = """() => {
  document.getElementById('runId').textContent = 'run_20260729_141233';
  document.getElementById('fileName').textContent = 'test_auto_20260729_141233.py';
  document.getElementById('ideOpen').dataset.state = 'ready';
}"""

_OVERFLOW = """() => ({
  doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  body: document.body.scrollWidth - document.body.clientWidth,
})"""


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        pw = sync_playwright().start()
    except Exception:
        return False
    try:
        browser = pw.chromium.launch()
        browser.close()
        return True
    except Exception:
        return False
    finally:
        pw.stop()


@pytest.fixture(scope="module")
def page():
    """A Chromium page with the playground loaded from file://.

    file:// is deliberate: this measures layout, so it must not depend on a running
    FastAPI server. The SSE connection simply fails and the bar renders its
    disconnected state, which does not affect header geometry.
    """
    if not _chromium_available():
        pytest.skip("Chromium not installed for Playwright")
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch()
    pg = browser.new_page(viewport={"width": 1920, "height": 900})
    pg.goto(_INDEX.as_uri(), wait_until="domcontentloaded")
    pg.wait_for_timeout(600)
    try:
        yield pg
    finally:
        browser.close()
        pw.stop()


@pytest.mark.parametrize("populated", [False, True], ids=["idle", "populated"])
def test_no_horizontal_overflow_at_any_width(page, populated):
    """The page never scrolls sideways — the check the earlier sweep omitted."""
    page.set_viewport_size({"width": 1920, "height": 900})
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    if populated:
        page.evaluate(_POPULATE)
        page.wait_for_timeout(120)

    offenders = []
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(90)
        over = page.evaluate(_OVERFLOW)
        if over["doc"] > 0 or over["body"] > 0:
            offenders.append((width, over["doc"], over["body"]))

    assert not offenders, (
        "horizontal overflow (width, documentElement, body): "
        f"{offenders}"
    )


_ROWS = """() => {
  const h = document.querySelector('header');
  const centres = [];
  for (const c of h.children) {
    const r = c.getBoundingClientRect();
    if (r.width === 0) continue;                 // display:none children
    const cy = (r.top + r.bottom) / 2;
    if (!centres.some(y => Math.abs(y - cy) < 6)) centres.push(cy);
  }
  return centres.length;
}"""

# The status chip's width depends on its label, and the label depends on ambient
# connection state — measured: Live 61px, Idle 59px, Connecting 109px,
# Disconnected 122px. So the row count is only well-defined per state.
_SET_STATUS = """([state, label]) => {
  const el = document.getElementById('status');
  el.dataset.state = state;
  el.querySelector('.label').textContent = label;
}"""


def test_gap_tightening_keeps_the_bar_on_one_row_at_1400(page):
    """Guards the gap-tightening media queries: measured, they are what keeps the
    populated bar single-row at 1400px (without them it wraps there).

    1400, not 1366: at 1366 the bar wraps once the status label is the long
    "Connecting"/"Disconnected" text, and that is fine — wrapping is the designed
    behaviour and `test_no_horizontal_overflow_at_any_width` is the real guard.
    Asserting 1366 here would be asserting a ~6px margin that depends on whether a
    server happens to be up.
    """
    page.set_viewport_size({"width": 1920, "height": 900})
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    page.evaluate(_POPULATE)
    page.evaluate(_SET_STATUS, ["idle", "Idle"])
    page.set_viewport_size({"width": 1400, "height": 900})
    page.wait_for_timeout(150)

    assert page.evaluate(_ROWS) == 1, (
        f"populated header wrapped into {page.evaluate(_ROWS)} rows at 1400px — "
        "the gap-tightening media queries are probably gone"
    )


@pytest.mark.parametrize(
    "state,label",
    [("live", "Live"), ("idle", "Idle"), ("connecting", "Connecting"),
     ("disconnected", "Disconnected")],
)
def test_header_wraps_gracefully_in_every_status_state(page, label, state):
    """Whatever the status label, wrapping must stay bounded and never overflow."""
    page.set_viewport_size({"width": 1920, "height": 900})
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    page.evaluate(_POPULATE)
    page.evaluate(_SET_STATUS, [state, label])

    for width in (1512, 1440, 1366, 1280, 1100, 900):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(120)
        over = page.evaluate(_OVERFLOW)
        assert over["doc"] == 0 and over["body"] == 0, (
            f"{label} at {width}px overflows: {over}"
        )
        assert page.evaluate(_ROWS) <= 2, (
            f"{label} at {width}px wrapped into {page.evaluate(_ROWS)} rows"
        )


def test_header_min_height_allows_wrapping(page):
    """A fixed `height` would clip wrapped rows; assert the header grows instead."""
    page.set_viewport_size({"width": 1920, "height": 900})
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    page.evaluate(_POPULATE)

    def measure():
        h = page.evaluate(
            """() => {
          const el = document.querySelector('header');
          return {box: el.getBoundingClientRect().height, content: el.scrollHeight};
        }"""
        )
        return h

    page.set_viewport_size({"width": 1512, "height": 900})
    page.wait_for_timeout(150)
    wide = measure()
    page.set_viewport_size({"width": 480, "height": 900})
    page.wait_for_timeout(150)
    narrow = measure()

    assert wide["box"] >= 52, f"header shorter than its 52px min-height: {wide}"
    assert narrow["box"] > wide["box"], (
        f"header did not grow when wrapping (wide={wide}, narrow={narrow})"
    )
    # scrollHeight > clientHeight would mean wrapped rows are being clipped.
    assert narrow["content"] <= narrow["box"] + 1, f"wrapped rows clipped: {narrow}"


def test_closed_drawer_is_not_keyboard_reachable(page):
    """The closed drawer sits off-screen at translateX(100%); it must not be tabbable.

    Regression guard for three measured failures: its pin/close/search controls were
    reachable by Tab while invisible, opening it never moved focus in, and Escape did
    not close it.
    """
    page.set_viewport_size({"width": 1512, "height": 945})
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(600)

    assert page.evaluate(
        "() => document.getElementById('treeDrawer').hasAttribute('inert')"
    ), "closed drawer is not inert"

    reached = page.evaluate(
        """() => {
      const ids = ['treePinBtn','treeCloseBtn','treeSearchInput','treeSearchClear'];
      const drawer = document.getElementById('treeDrawer');
      // inert removes descendants from the tab order; assert via focusability
      return ids.filter(id => {
        const el = document.getElementById(id);
        if (!el) return false;
        el.focus();
        return document.activeElement === el;
      });
    }"""
    )
    assert not reached, f"focusable controls inside a closed drawer: {reached}"
    assert not page.evaluate(
        "() => document.getElementById('treeDrawer').contains(document.activeElement)"
    ), "focus ended up inside the closed drawer"


def test_open_drawer_takes_focus_and_escape_closes_it(page):
    page.set_viewport_size({"width": 1512, "height": 945})
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(600)

    page.evaluate("() => document.querySelector('.tree-toggle-tab').click()")
    page.wait_for_timeout(350)
    assert page.evaluate(
        "() => document.getElementById('treeDrawer').contains(document.activeElement)"
    ), "opening the drawer did not move focus into it"
    assert not page.evaluate(
        "() => document.getElementById('treeDrawer').hasAttribute('inert')"
    ), "open drawer is still inert"

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.evaluate(
        "() => document.getElementById('treeDrawer').classList.contains('is-open')"
    ), "Escape did not close the drawer"
    assert page.evaluate(
        "() => document.activeElement === document.getElementById('treeToggleTab')"
    ), "focus was not returned to the toggle tab (it must not stay in an inert subtree)"


def test_pinned_drawer_is_never_visible_while_logically_closed(page):
    """Pinned CSS overrides the closed transform, so pinned+closed showed a visible
    panel that `showTreeForStep`'s `if (!isOpen) return` then never updated — it sat
    on "Waiting for the first step" forever while steps arrived. Pin and open are
    one state.
    """
    page.set_viewport_size({"width": 1512, "height": 945})
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(600)

    state = """() => {
      const d = document.getElementById('treeDrawer');
      const r = d.getBoundingClientRect();
      return {onScreen: r.left < window.innerWidth - 1,
              isOpen: d.classList.contains('is-open')};
    }"""

    page.evaluate("() => document.getElementById('treePinBtn').click()")
    page.wait_for_timeout(350)
    after_pin = page.evaluate(state)
    assert after_pin["isOpen"], f"pinning left the drawer logically closed: {after_pin}"

    page.evaluate("() => document.getElementById('treeCloseBtn').click()")
    page.wait_for_timeout(350)
    after_close = page.evaluate(state)
    assert not after_close["onScreen"], (
        f"closed drawer still on-screen — pin was not released: {after_close}"
    )

    # Below the 1360px pin breakpoint the pinned drawer is absolutely positioned and
    # would overlay the workspace, so check the boundary too.
    for width in (1360, 1359, 1200):
        page.set_viewport_size({"width": width, "height": 900})
        page.evaluate("() => window.DomTreePanel.open()")
        page.evaluate("() => document.getElementById('treePinBtn').click()")
        page.wait_for_timeout(300)
        assert page.evaluate(state)["isOpen"], f"pinned but closed at {width}px"
        page.evaluate("() => window.DomTreePanel.close()")
        page.wait_for_timeout(300)
        closed = page.evaluate(state)
        assert not closed["onScreen"], f"visible-but-closed at {width}px: {closed}"
