"""P3a: richer web interaction actions — scroll_into_view, select, upload,
double_click, right_click, drag.

These close the "can't automate forms / off-viewport elements" gap vs Midscene
and Playwright. They are web-first (Playwright has clean, stable APIs for each;
select/upload/right_click have no touch equivalent, and scroll/dblclick/drag are
coordinate-based on uiautomator2 which P2 deliberately stopped emitting). Mobile
parity is tracked separately; the capability matrix documents the web-only scope.

Contracts pinned here (TDD): each handler's execute() verdict + the exact
Playwright API its generate_code() emits. Live runnability is proven against real
Chromium in tests/test_web_smoke_live.py.
"""

import ast

from common.executor import (
    DoubleClickHandler,
    DragHandler,
    RightClickHandler,
    ScrollIntoViewHandler,
    SelectHandler,
    UploadHandler,
)


class _WebEl:
    """Minimal Playwright-locator stand-in recording the calls made on it."""

    def __init__(self, *, raise_on=None):
        self.calls = []
        self._raise_on = raise_on or set()

    @property
    def first(self):
        # Real Playwright locators expose .first returning a locator; the
        # production target-resolver calls d.locator(sel).first.
        return self

    def _maybe_raise(self, name):
        if name in self._raise_on:
            raise TimeoutError(f"{name} timed out")

    def wait_for(self, state="visible", timeout=0):
        self._maybe_raise("wait_for")

    def scroll_into_view_if_needed(self, timeout=0):
        self._maybe_raise("scroll_into_view_if_needed")
        self.calls.append("scroll")

    def select_option(self, value, timeout=0):
        self._maybe_raise("select_option")
        self.calls.append(("select", value))

    def set_input_files(self, files, timeout=0):
        self._maybe_raise("set_input_files")
        self.calls.append(("upload", files))

    def dblclick(self, timeout=0):
        self._maybe_raise("dblclick")
        self.calls.append("dblclick")

    def click(self, button="left", timeout=0):
        self._maybe_raise("click")
        self.calls.append(("click", button))

    def drag_to(self, target, timeout=0):
        self._maybe_raise("drag_to")
        self.calls.append(("drag_to", target))


class _DragDevice:
    """Device exposing locator factories so DragHandler can resolve the target
    (extra_value) into a live handle, with auto-detected locator type."""

    def __init__(self):
        self.resolved = []

    def locator(self, sel):
        self.resolved.append(("css", sel))
        return _WebEl()

    def get_by_text(self, txt):
        self.resolved.append(("text", txt))
        return _WebEl()


def _parses(code_lines):
    """Generated step lines must form valid Python under a fixture function."""
    src = "import allure\nfrom common.logs import log\n\ndef _g(d):\n" + "".join(code_lines)
    ast.parse(src)


class TestScrollIntoView:
    def test_execute_scrolls(self):
        el = _WebEl()
        assert ScrollIntoViewHandler().execute(None, el, "web", "") is True
        assert "scroll" in el.calls

    def test_execute_timeout_fails(self):
        el = _WebEl(raise_on={"scroll_into_view_if_needed"})
        assert ScrollIntoViewHandler().execute(None, el, "web", "") is False

    def test_codegen_emits_scroll_into_view_if_needed(self):
        code = ScrollIntoViewHandler().generate_code("web", "css", "#far", "", 30.0)
        joined = "".join(code)
        assert "scroll_into_view_if_needed" in joined
        _parses(code)


class TestSelect:
    def test_execute_selects(self):
        el = _WebEl()
        assert SelectHandler().execute(None, el, "web", "Option B") is True
        assert ("select", "Option B") in el.calls

    def test_execute_timeout_fails(self):
        el = _WebEl(raise_on={"select_option"})
        assert SelectHandler().execute(None, el, "web", "X") is False

    def test_codegen_emits_select_option(self):
        code = SelectHandler().generate_code("web", "css", "#country", "US", 30.0)
        joined = "".join(code)
        assert "select_option('US'" in joined
        _parses(code)


class TestUpload:
    def test_execute_uploads(self):
        el = _WebEl()
        assert UploadHandler().execute(None, el, "web", "/tmp/a.png") is True
        assert ("upload", "/tmp/a.png") in el.calls

    def test_codegen_emits_set_input_files(self):
        code = UploadHandler().generate_code("web", "css", "#file", "/tmp/a.png", 30.0)
        joined = "".join(code)
        assert "set_input_files('/tmp/a.png'" in joined
        _parses(code)


class TestDoubleClick:
    def test_execute_dblclicks(self):
        el = _WebEl()
        assert DoubleClickHandler().execute(None, el, "web", "") is True
        assert "dblclick" in el.calls

    def test_codegen_emits_dblclick(self):
        code = DoubleClickHandler().generate_code("web", "text", "Item", "", 30.0)
        joined = "".join(code)
        assert "dblclick" in joined
        _parses(code)


class TestRightClick:
    def test_execute_right_clicks(self):
        el = _WebEl()
        assert RightClickHandler().execute(None, el, "web", "") is True
        assert ("click", "right") in el.calls

    def test_codegen_emits_button_right(self):
        code = RightClickHandler().generate_code("web", "text", "Row", "", 30.0)
        joined = "".join(code)
        assert "button='right'" in joined
        _parses(code)


class TestDrag:
    def test_execute_drags_to_target(self):
        # Source element is resolved; target comes from extra_value via the device.
        src = _WebEl()
        dev = _DragDevice()
        assert DragHandler().execute(dev, src, "web", "#dropzone") is True
        assert any(c[0] == "drag_to" for c in src.calls), "drag_to not called on source"
        assert ("css", "#dropzone") in dev.resolved

    def test_execute_target_text_autodetected(self):
        src = _WebEl()
        dev = _DragDevice()
        DragHandler().execute(dev, src, "web", "Trash")  # no #/./@ → text
        assert ("text", "Trash") in dev.resolved

    def test_codegen_emits_drag_to(self):
        code = DragHandler().generate_code("web", "css", "#item", "#bin", 30.0)
        joined = "".join(code)
        assert "drag_to" in joined
        assert "#bin" in joined
        _parses(code)


class TestActionsRegisteredAndInVocab:
    """All 6 new actions must be wired through every vocabulary point so the
    workflow schema, tool protocol, and LLM prompts accept them."""

    NEW = ["scroll_into_view", "select", "upload", "double_click", "right_click", "drag"]

    def test_in_supported_actions(self):
        from common.capabilities import SUPPORTED_ACTIONS
        for a in self.NEW:
            assert a in SUPPORTED_ACTIONS, f"{a} missing from SUPPORTED_ACTIONS"

    def test_registered_in_executor(self):
        from common.executor import UIExecutor
        ex = UIExecutor(object(), platform="web")
        for a in self.NEW:
            assert a in ex._handlers, f"{a} not registered in UIExecutor._handlers"

    def test_extra_value_actions(self):
        from common.capabilities import ACTIONS_REQUIRING_EXTRA_VALUE
        # select/upload/drag carry a payload; scroll/dblclick/rightclick don't.
        for a in ("select", "upload", "drag"):
            assert a in ACTIONS_REQUIRING_EXTRA_VALUE
        for a in ("scroll_into_view", "double_click", "right_click"):
            assert a not in ACTIONS_REQUIRING_EXTRA_VALUE

    def test_workflow_schema_accepts(self):
        from common.workflow_schema import WorkflowStep
        WorkflowStep(action="select", locator_type="css", locator_value="#c", extra_value="US")
        WorkflowStep(action="scroll_into_view", locator_type="css", locator_value="#x")

    def test_tool_protocol_accepts(self):
        from common.tool_protocol import ActionToolControl
        ActionToolControl(action="drag", locator_type="css", locator_value="#a", extra_value="#b")
        ActionToolControl(action="double_click", locator_type="text", locator_value="Item")

    def test_tool_protocol_assert_url_needs_no_locator(self):
        # Regression: ActionToolControl used a hardcoded {goto,swipe,press} set,
        # so assert_url (a global, no-locator action) was wrongly rejected for
        # missing a locator. It must validate with extra_value only.
        from common.tool_protocol import ActionToolControl
        ActionToolControl(action="assert_url", extra_value="/dashboard")
