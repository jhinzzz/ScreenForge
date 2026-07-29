"""Live theme-consistency tests for playground/index.html against a real Chromium.

WHY THIS EXISTS: the accent colours were tokenized per theme (`--blue`, `--live`,
…) but the ~38 rules that needed an accent at their own alpha spelled the DARK
channels out longhand — `rgba(110,231,183,0.08)` — in global, non-themed rules. So
on the light theme a chip's *text* followed the theme while its own border and
background stayed dark-theme: the live status pill was `#047857` text inside an
`rgb(110,231,183)` border. Grep could not catch the reverse either, because
`var()` inside `rgba()` that fails is invalid at computed-value time — it renders
**transparent, silently, with no console error**. Only computed values prove it.

Two properties are asserted:

1. Every accent wash/border follows its theme (no dark channels leaking onto paper,
   and nothing silently transparent).
2. Accent text clears WCAG AA against the wash it actually sits on. This is the
   subtle one: each chip tints its own background with the same accent it writes
   in, so once the wash follows the theme it sits *closer* to the text. Three
   light hexes cleared 4.5:1 on bare paper but measured 4.12-4.48:1 on their own
   chip, and had to be darkened.

Deliberately excluded: `.shot-live-tag` and the other `--on-shot*` users. They sit
on the app-under-test's imagery, which is always dark, so they are pinned bright in
BOTH themes on purpose — a "follows the theme" assertion there would be backwards.
They still get the AA check, against that dark ink.

OPT-IN: RUN_LIVE_WEB_SMOKE=1 pytest tests/test_playground_theme_live.py -v
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
        reason="Live theme smoke is opt-in. Set RUN_LIVE_WEB_SMOKE=1 (needs real Chromium).",
    ),
]

_INDEX = Path(__file__).resolve().parent.parent / "playground" / "index.html"

# Composites an element's background down through its ancestors, then ratios its
# text colour against the result — i.e. the contrast a person actually sees, not
# the contrast against a bare panel.
_HELPERS = r"""
window.__aa = (() => {
  const lum = ([r, g, b]) => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b);
  };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + .05) / (y + .05); };
  const parse = s => (s.match(/[\d.]+/g) || []).map(Number);
  const flatten = el => {
    const stack = [];
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      stack.push(parse(getComputedStyle(n).backgroundColor));
    }
    stack.push(parse(getComputedStyle(document.documentElement).backgroundColor));
    let out = [255, 255, 255];
    for (const c of stack.reverse()) {
      if (c.length < 3) continue;
      const a = c.length > 3 ? c[3] : 1;
      out = out.map((o, i) => o * (1 - a) + c[i] * a);
    }
    return out.map(Math.round);
  };
  return (el, name) => {
    const cs = getComputedStyle(el), fg = parse(cs.color).slice(0, 3), bg = flatten(el);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    return {name, size, fg: `rgb(${fg})`, bg: `rgb(${bg})`,
            ratio: Math.round(ratio(fg, bg) * 100) / 100, need};
  };
})();
"""

_STATES = ("live", "connecting", "idle", "disconnected")


@pytest.fixture(scope="module")
def page():
    if not _chromium_available():
        pytest.skip("Chromium not installed for Playwright")
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch()
    pg = browser.new_page(viewport={"width": 1512, "height": 945})
    pg.goto(_INDEX.as_uri(), wait_until="domcontentloaded")
    pg.wait_for_timeout(700)
    pg.add_script_tag(content=_HELPERS)
    # .status has `transition: background .25s, color .25s, border-color .25s`, so a
    # synchronous read right after flipping data-state samples a half-finished fade
    # and every state reports the same mid-transition colour. Kill transitions.
    pg.add_style_tag(
        content="*,*::before,*::after{transition:none!important;animation:none!important}"
    )
    try:
        yield pg
    finally:
        browser.close()
        pw.stop()


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


def _set_theme(page, theme):
    page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
    page.wait_for_timeout(120)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_accent_washes_follow_the_theme(page, theme):
    """A chip's border/background must be the same hue family as its own text.

    Catches both failure modes: a dark channel hardcoded into a global rule (the
    original bug) and a `var()` that fails and renders transparent (the fix's own
    risk — silent, no console error).
    """
    _set_theme(page, theme)
    offenders = []
    for state in _STATES:
        page.evaluate(
            """(s) => { const el = document.getElementById('status');
              el.dataset.state = s; el.querySelector('.label').textContent = s; }""",
            state,
        )
        page.wait_for_timeout(80)
        vals = page.evaluate(
            """() => {
          const el = document.getElementById('status'), cs = getComputedStyle(el);
          const p = s => (s.match(/[\\d.]+/g) || []).map(Number);
          return {text: p(cs.color).slice(0, 3),
                  border: p(cs.borderColor), bg: p(cs.backgroundColor)};
        }"""
        )
        # alpha > 0: a failed var() collapses to rgba(0,0,0,0)
        for part in ("border", "bg"):
            chan = vals[part]
            alpha = chan[3] if len(chan) > 3 else 1
            if alpha == 0:
                offenders.append(f"{state}.{part} is transparent (a var() failed): {chan}")
                continue
            # EXACT match against the text's own colour, which is `color: var(--x)`
            # — the border and background are that same accent at a lower alpha, so
            # getComputedStyle's rgba() carries the channel unmixed and the triples
            # must be equal. Fuzzy comparisons are all too weak here: dark #6ee7b7
            # and light #047857 share channel ordering (G>B>R) AND sit only 7° apart
            # in hue, so both an ordering check and a hue check pass on the very bug
            # this test exists to catch. Only equality distinguishes them.
            if tuple(chan[:3]) != tuple(vals["text"]):
                offenders.append(
                    f"{state}.{part} rgb{tuple(chan[:3])} != its text "
                    f"rgb{tuple(vals['text'])} — the wash is not the themed accent"
                )
    assert not offenders, f"[{theme}] " + "; ".join(offenders)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_accent_text_clears_wcag_aa_on_its_own_wash(page, theme):
    """Accent text must clear AA against the wash it sits on, not against bare paper.

    Guards the deepened light hexes: at #2563eb / #b45309 / #047857 the status chips
    measured 4.23 / 4.12 / 4.48:1 here while clearing 4.5 on the plain panel.
    """
    _set_theme(page, theme)
    results = []
    for state in _STATES:
        page.evaluate(
            """(s) => { const el = document.getElementById('status');
              el.dataset.state = s; el.querySelector('.label').textContent = s; }""",
            state,
        )
        page.wait_for_timeout(80)
        results.append(
            page.evaluate(
                "(s) => window.__aa(document.querySelector('#status .label'), 'status ' + s)",
                state,
            )
        )

    # The frame badge, in both variants. Pinned bright in both themes (--on-shot-live
    # /-amber) because it sits on the always-dark screenshot; using the themed accents
    # there measured 1.63:1 and 1.78:1 on light.
    for cls, name in (("", "shot-live-tag live"), ("idle", "shot-live-tag idle")):
        page.evaluate(
            """(cls) => { const f = document.querySelector('.shot-frame');
              f.classList.remove('idle'); if (cls) f.classList.add(cls); }""",
            cls,
        )
        page.wait_for_timeout(80)
        results.append(
            page.evaluate(
                "(n) => window.__aa(document.querySelector('.shot-live-tag'), n)", name
            )
        )

    failures = [r for r in results if r["ratio"] < r["need"]]
    assert not failures, f"[{theme}] WCAG AA failures: " + "; ".join(
        f"{r['name']} {r['ratio']}:1 (need {r['need']}) {r['fg']} on {r['bg']}"
        for r in failures
    )


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_ide_glyph_follows_the_theme(page, theme):
    """The IDE button's SVG hardcoded the dark theme's hexes, so the glyph stayed
    dark blue on paper while the button around it went light. `var()` does work in
    SVG presentation attributes; assert it actually resolved.
    """
    _set_theme(page, theme)
    vals = page.evaluate(
        """() => {
      const p = document.querySelector('#ideGo svg path'), cs = getComputedStyle(p);
      return {fill: cs.fill, stroke: cs.stroke,
              border: getComputedStyle(document.getElementById('ideGo')).borderColor};
    }"""
    )
    for part in ("fill", "stroke"):
        assert vals[part] not in ("none", "", "rgba(0, 0, 0, 0)"), (
            f"[{theme}] IDE glyph {part} did not resolve: {vals}"
        )

    def lightness(css):
        c = [float(x) for x in (css.replace("rgb(", "").replace(")", "").split(","))[:3]]
        return sum(c) / 3

    # Both themes must agree on direction: on paper the glyph and its button border
    # are dark-on-light, in the dark theme light-on-dark. If the SVG stopped
    # following the theme, these two would disagree.
    if theme == "light":
        assert lightness(vals["stroke"]) < 200, (
            f"light-theme glyph stroke is not an ink colour: {vals}"
        )
    else:
        assert lightness(vals["stroke"]) > 100, (
            f"dark-theme glyph stroke went dark: {vals}"
        )
