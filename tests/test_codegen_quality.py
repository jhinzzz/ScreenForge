"""P2: generated-test-code quality — goal-derived naming, coordinate-click
honesty (no pixel clicks baked into persisted tests), and human-readable
allure.step labels (no stale @N refs).

These pin the contracts the audit flagged: a "runnable test" must carry the
user's intent in its name, must never silently rot via a hardcoded coordinate,
and must read cleanly in the Allure report.
"""

import ast

from cli.shared import get_initial_header
from common.executor import (
    LocatorBuilder,
    build_fallback_locator,
)


class TestGoalDerivedNaming:
    """get_initial_header(label=...) names the test after the user's goal."""

    def test_default_label_keeps_legacy_name(self):
        # No label → unchanged behavior (main.py + public-surface contract safe).
        header = "".join(get_initial_header())
        assert "def test_auto_generated_case(d):" in header

    def test_label_becomes_function_name(self):
        header = "".join(get_initial_header(label="Login with valid credentials"))
        assert "def test_login_with_valid_credentials(d):" in header

    def test_label_flows_into_docstring_and_story(self):
        header = "".join(get_initial_header(label="Search for a product"))
        assert "Search for a product" in header  # docstring or allure.story carries intent

    def test_unicode_label_is_preserved(self):
        # Chinese goals are the common case here; PEP 3131 allows unicode
        # identifiers, so the slug must NOT strip them to an empty name.
        header = "".join(get_initial_header(label="登录成功"))
        assert "def test_" in header
        # function name is a valid python identifier
        for line in header.splitlines():
            if line.startswith("def test_"):
                name = line[len("def "):].split("(")[0]
                assert name.isidentifier(), f"{name!r} is not a valid identifier"

    def test_header_is_valid_python(self):
        for label in (None, "Buy item #3!", "登录/退出", "   ", "123 starts with digit"):
            header = "".join(get_initial_header(label=label))
            # header is an incomplete function (no body) — add a pass to parse
            ast.parse(header + "    pass\n")

    def test_label_with_only_symbols_falls_back(self):
        # A label that slugs to empty must not produce `def test_(d):`.
        header = "".join(get_initial_header(label="!!!"))
        for line in header.splitlines():
            if line.startswith("def test_"):
                name = line[len("def "):].split("(")[0]
                assert name.isidentifier() and name != "test_"

    def test_no_unused_pytest_import_still(self):
        # Regression: the P1 F401 fix must survive (header stays pytest-free).
        assert "import pytest" not in "".join(get_initial_header(label="anything"))

    def test_control_chars_in_label_dont_break_emitted_file(self):
        # \r and NUL in a string literal make the emitted file unparseable;
        # they must be stripped before the label lands in story/docstring.
        for label in ("carriage\rreturn", "null\x00byte", "crlf\r\nline", "tab\tsep"):
            header = "".join(get_initial_header(label=label))
            ast.parse(header + "    pass\n")

    def test_unicode_nonidentifier_chars_fall_back(self):
        # \w matches fractions/superscripts that are NOT valid identifier chars;
        # the slug must fall back rather than emit `def test_½_half`.
        for label in ("½ half", "²power", "¼", "Ⅷ ok"):
            header = "".join(get_initial_header(label=label))
            ast.parse(header + "    pass\n")
            for line in header.splitlines():
                if line.startswith("def test_"):
                    name = line[len("def "):].split("(")[0]
                    assert name.isidentifier(), f"{name!r} is not a valid identifier"


class TestBuildFallbackLocator:
    """build_fallback_locator picks the most stable Playwright locator from the
    element's remaining attributes — never a coordinate. Precedence:
    id > name > role+accessible-name > label(desc) > placeholder > text > None."""

    def test_id_wins(self):
        frag = build_fallback_locator({"id": "submit", "name": "go", "text": "Go"})
        assert frag == "locator('#submit').first"

    def test_name_attr_preferred_over_role(self):
        # name is unique by spec — prefer it over a possibly-duplicated role+name.
        frag = build_fallback_locator({"class": "button", "clickable": True,
                                       "name": "username", "text": "User"})
        assert "[name=\"username\"]" in frag

    def test_role_with_accessible_name(self):
        frag = build_fallback_locator({"class": "button", "clickable": True, "desc": "Submit"})
        assert "get_by_role('button'" in frag
        assert "Submit" in frag

    def test_link_role_inferred_from_anchor(self):
        frag = build_fallback_locator({"class": "a", "clickable": True, "text": "Home"})
        assert "get_by_role('link'" in frag

    def test_label_from_desc_when_role_unclear(self):
        frag = build_fallback_locator({"class": "div", "clickable": False, "desc": "Close dialog"})
        assert "get_by_label('Close dialog')" in frag or "get_by_role(" in frag

    def test_placeholder_for_form_field(self):
        frag = build_fallback_locator({"class": "input", "type": "text", "placeholder": "Email"})
        assert "get_by_placeholder('Email')" in frag

    def test_text_as_last_resort(self):
        frag = build_fallback_locator({"class": "span", "text": "Total"})
        assert "get_by_text('Total')" in frag

    def test_no_attrs_returns_none(self):
        # Bare class + coordinates → no locator possible (visual-fallback shape).
        assert build_fallback_locator({"class": "div", "x": 1, "y": 2, "w": 3, "h": 4}) is None

    def test_name_with_quote_is_escaped(self):
        # A name containing " must not prematurely close the [name="..."] selector.
        frag = build_fallback_locator({"name": 'we"ird'})
        assert frag is not None
        # The emitted fragment must be a valid python string literal.
        ast.parse(f"d.{frag}")
        assert '\\"' in frag  # the inner quote is backslash-escaped

    def test_id_with_special_chars_is_escaped(self):
        # An id like "weird.id" must not be parsed as id + class selector.
        frag = build_fallback_locator({"id": "weird.id"})
        assert frag is not None
        ast.parse(f"d.{frag}")
        assert "\\." in frag


class TestScopedLocatorDisambiguation:
    """When N controls share an accessible name (e.g. one 'Delete' per row), the
    compressor flags them with `scope` (the row's identifying text). codegen must
    emit a SCOPED locator that targets the right one — and crucially must NOT
    append `.first`, which silently picks row 1 (the lie). Playwright strict-mode
    then enforces honesty: a scope that isn't unique fails loud at replay."""

    def test_scoped_locator_omits_first(self):
        # The single highest-value assertion: a scoped element must NOT degrade to
        # `.first` (always row 1). It must scope by the row label and still target
        # the button by role+name.
        frag = build_fallback_locator({
            "class": "button", "clickable": True, "text": "Delete",
            "scope": "Bob Jones",
        })
        assert frag is not None
        assert ".first" not in frag, (
            "scoped locator degraded to .first — persisted test always clicks row 1"
        )
        assert "Bob Jones" in frag, "scope (row label) not used to disambiguate"
        assert "get_by_role('button'" in frag and "Delete" in frag, (
            "scoped locator lost the inner role+name strategy"
        )
        # Must be a valid python locator expression.
        ast.parse(f"d.{frag}")

    def test_scope_composes_with_text_inner_when_no_role(self):
        # A non-role element (e.g. a clickable span) that is ambiguous still scopes.
        frag = build_fallback_locator({
            "class": "span", "clickable": True, "text": "Edit", "scope": "Row 7",
        })
        assert frag is not None
        assert ".first" not in frag
        assert "Row 7" in frag
        ast.parse(f"d.{frag}")

    def test_unambiguous_element_unchanged_no_scope(self):
        # Regression guard: an element WITHOUT scope keeps the existing behavior
        # (this is the common case — must not change, and .first stays allowed).
        frag = build_fallback_locator({"class": "button", "clickable": True, "text": "Save"})
        assert frag == "get_by_role('button', name='Save').first"

    def test_known_ambiguous_but_unscopable_returns_none_not_first(self):
        # The honesty boundary: an element flagged ambiguous (it has dup_index, so
        # it was in a >=2 collision group) but for which NO scope could be computed
        # must NOT emit get_by_text('Delete').first (silently row 1 — the lie). It
        # returns None so the caller takes the honest pytest.skip path.
        frag = build_fallback_locator({
            "class": "button", "clickable": True, "text": "Delete", "dup_index": 1,
        })
        assert frag is None, (
            f"known-ambiguous-but-unscopable element emitted {frag!r} — the silent "
            ".first lie this feature exists to kill"
        )

    def test_empty_scope_with_dup_index_also_returns_none(self):
        # computeScope can return '' (row root found but no distinguishing text).
        # Empty scope + dup_index is still "ambiguous and unscopable" → None.
        frag = build_fallback_locator({
            "class": "button", "clickable": True, "text": "Delete",
            "scope": "", "dup_index": 2,
        })
        assert frag is None

    def test_no_nth_ever_emitted_for_dup_index(self):
        # Positional .nth(k) is a coordinate-by-another-name (brittle to reorder);
        # it must never appear, scoped or not.
        for el in (
            {"class": "button", "clickable": True, "text": "Delete", "dup_index": 0},
            {"class": "button", "clickable": True, "text": "Delete", "scope": "Bob", "dup_index": 1},
        ):
            frag = build_fallback_locator(el)
            assert frag is None or ".nth(" not in frag


class TestScopedLocatorLockstep:
    """The emitted codegen string (build_code/build_fallback_locator) and the live
    handle (get_element/get_fallback_element) must resolve to the SAME element for
    a scoped ref — and an unscopable-ambiguous ref must NOT silently resolve live
    to row 1 while emitting something else. Both sides flow through one strategy."""

    def _resolve(self, elements):
        return lambda r: next((e for e in elements if e.get("ref") == r), None)

    def test_build_code_for_scoped_ref_uses_scope_not_first(self):
        els = [{"ref": "@4", "class": "button", "clickable": True,
                "text": "Delete", "scope": "Bob Jones", "dup_index": 1,
                "x": 1, "y": 2, "w": 3, "h": 4}]
        code = LocatorBuilder.build_code("web", "ref", "@4", resolve_ref=self._resolve(els))
        assert "Bob Jones" in code, "scoped ref didn't emit the row-scoped locator"
        assert "mouse.click" not in code

    def test_unscopable_ambiguous_ref_does_not_emit_wrong_first(self):
        # @4 is known-ambiguous (dup_index) but unscopable (no scope). build_code
        # must NOT emit get_by_text('Delete').first (row 1) NOR a bogus
        # locator('@4') raw-ref selector. It should yield the honest skip/None
        # path — i.e. no get_by_text('Delete').first and no raw '@4' selector.
        els = [{"ref": "@4", "class": "button", "clickable": True,
                "text": "Delete", "dup_index": 1, "x": 1, "y": 2, "w": 3, "h": 4}]
        code = LocatorBuilder.build_code("web", "ref", "@4", resolve_ref=self._resolve(els))
        assert "get_by_text('Delete').first" not in code, (
            "unscopable-ambiguous ref emitted the silent row-1 lie"
        )
        assert "locator('@4')" not in code, (
            "emitted the raw @N ref token as a CSS selector (invalid)"
        )

    def test_get_element_for_unscopable_ambiguous_ref_is_none(self):
        # The LIVE side must also refuse to resolve an unscopable-ambiguous ref to
        # row 1 (get_by_text('Delete').first) — otherwise the live click and the
        # persisted locator diverge. None here routes to the honest skip path.
        from common.executor import LocatorBuilder as LB

        class _Dev:
            def get_by_text(self, *a, **k): raise AssertionError(
                "live resolution fell back to get_by_text for an ambiguous ref (row-1 lie)")
            def locator(self, *a, **k): raise AssertionError("raw-ref locator on live side")

        els = [{"ref": "@4", "class": "button", "clickable": True,
                "text": "Delete", "dup_index": 1, "x": 1, "y": 2, "w": 3, "h": 4}]
        handle = LB.get_element(_Dev(), "web", "ref", "@4", resolve_ref=self._resolve(els))
        assert handle is None, "unscopable-ambiguous ref must resolve live to None (→ skip)"


class TestBuildCodeNeverEmitsCoordinates:
    """The codegen path must never bake a pixel click into a persisted test."""

    def setup_method(self):
        self.elements = [
            {"ref": "@1", "id": "ok", "text": "OK", "x": 1, "y": 2, "w": 3, "h": 4},
            {"ref": "@2", "class": "button", "clickable": True, "desc": "Save",
             "x": 1, "y": 2, "w": 3, "h": 4},
            {"ref": "@3", "class": "div", "x": 5, "y": 5, "w": 4, "h": 2},  # no attrs
        ]
        self.resolve = lambda r: next((e for e in self.elements if e["ref"] == r), None)

    def test_ref_with_attrs_uses_locator_not_coords(self):
        code = LocatorBuilder.build_code("web", "ref", "@2", resolve_ref=self.resolve)
        assert "mouse.click" not in code
        assert "get_by_role" in code or "[name=" in code or "get_by_label" in code

    def test_ref_without_any_attrs_does_not_emit_mouse_click(self):
        # @3 has no locatable attrs → must NOT emit a coordinate; a literal
        # locator that fails loudly is acceptable, a silent pixel click is not.
        code = LocatorBuilder.build_code("web", "ref", "@3", resolve_ref=self.resolve)
        assert "mouse.click" not in code


class _RefDevice:
    """Web device whose ref resolution always fails to produce a live locator,
    forcing the runtime coordinate fallback — but mouse.click succeeds so the
    'recording still works' guarantee holds."""

    def __init__(self):
        self.mouse = self
        self.clicked = []

    def click(self, x, y):
        self.clicked.append((x, y))


class TestReadableStepLabels:
    """allure.step labels must show the human-readable target, not a raw @N.

    Production builds labels inside each handler's generate_code, and the ONLY
    production caller is execute_and_record — so a single post-process there
    (humanize_step_labels) fixes every handler at once. We unit-test that pure
    transform here; the live web smoke proves the execute_and_record wiring.
    """

    def test_readable_ref_target_prefers_text_then_desc_then_id(self):
        from common.executor import readable_ref_target
        assert readable_ref_target({"ref": "@3", "text": "合约"}) == "合约"
        assert readable_ref_target({"ref": "@3", "desc": "Close"}) == "Close"
        assert readable_ref_target({"ref": "@3", "id": "go"}) == "go"
        # nothing readable → fall back to the ref token itself (never crash)
        assert readable_ref_target({"ref": "@3"}) == "@3"

    def test_humanize_replaces_ref_token_in_labels(self):
        from common.executor import humanize_step_labels
        lines = [
            "    with allure.step('Click: [@3]'):\n",
            "        log.info('Action: click [@3]')\n",
            "        d.get_by_text('合约').first.click(timeout=30000.0)\n",
        ]
        out = "".join(humanize_step_labels(lines, "@3", "合约"))
        assert "[@3]" not in out
        assert "合约" in out
        # the actual locator line is untouched (already resolved)
        assert "get_by_text('合约')" in out

    def test_humanize_is_noop_without_token(self):
        from common.executor import humanize_step_labels
        lines = ["    with allure.step('Click: [Login]'):\n"]
        assert humanize_step_labels(lines, "@9", "x") == lines
