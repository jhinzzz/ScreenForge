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
    UIExecutor,
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
