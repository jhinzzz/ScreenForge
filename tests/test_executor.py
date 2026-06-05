"""Tests for common/executor.py — ref cache, LocatorBuilder, handlers."""

import pytest

from common.executor import (
    AssertExistHandler,
    AssertNotExistHandler,
    AssertTextContainsHandler,
    AssertTextEqualsHandler,
    AssertUrlHandler,
    AssertValueHandler,
    ClickHandler,
    InputHandler,
    LocatorBuilder,
    SwipeHandler,
    UIExecutor,
    WaitForHandler,
)


class _RecordingDevice:
    """Records the method name called on it (for swipe dispatch checks)."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self.calls.append(name)
            return None
        return _call


class TestSwipeHandlerPlatformDispatch:
    """Regression for the iOS swipe bug (found on a real simulator):
    SwipeHandler called d.swipe_ext() — a uiautomator2/Android-only API — on
    every non-web platform, so swipe crashed on iOS with AttributeError. iOS
    must use facebook-wda's directional swipe_up/down/left/right()."""

    def test_ios_execute_uses_directional_swipe(self):
        dev = _RecordingDevice()
        assert SwipeHandler().execute(dev, None, "ios", "up") is True
        assert dev.calls == ["swipe_up"], f"expected swipe_up, got {dev.calls}"

    def test_ios_execute_never_calls_swipe_ext(self):
        dev = _RecordingDevice()
        for direction in ("up", "down", "left", "right"):
            SwipeHandler().execute(dev, None, "ios", direction)
        assert "swipe_ext" not in dev.calls
        assert dev.calls == ["swipe_up", "swipe_down", "swipe_left", "swipe_right"]

    def test_android_execute_still_uses_swipe_ext(self):
        dev = _RecordingDevice()
        SwipeHandler().execute(dev, None, "android", "up")
        assert dev.calls == ["swipe_ext"]

    def test_ios_generate_code_emits_directional(self):
        code = "".join(SwipeHandler().generate_code("ios", "", "", "left", 30.0))
        assert "d.swipe_left()" in code
        assert "swipe_ext" not in code

    def test_android_generate_code_emits_swipe_ext(self):
        code = "".join(SwipeHandler().generate_code("android", "", "", "up", 30.0))
        assert "d.swipe_ext('up')" in code

    def test_invalid_direction_defaults_to_down(self):
        dev = _RecordingDevice()
        SwipeHandler().execute(dev, None, "ios", "diagonal")
        assert dev.calls == ["swipe_down"]  # no swipe_diagonal attribute built
        code = "".join(SwipeHandler().generate_code("ios", "", "", "diagonal", 30.0))
        assert "d.swipe_down()" in code


class _WebElement:
    """Mimics a Playwright locator for assert handlers.

    wait_for is state-aware: an element that is not visible raises on
    wait_for(state="visible") (mirrors a real TimeoutError), and a visible
    element raises on wait_for(state="hidden") — so assert_not_exist / wait_for
    can be exercised with the same simple mock.
    """

    def __init__(self, *, visible=True, text="", value="", raise_on_wait=False):
        self._visible = visible
        self._text = text
        self._value = value
        self._raise = raise_on_wait
        self.last_state = None  # records the state= arg of the most recent wait_for

    def wait_for(self, state="visible", timeout=0):
        self.last_state = state
        if self._raise:
            raise TimeoutError("element not visible")
        if state == "visible" and not self._visible:
            raise TimeoutError("element never became visible")
        if state in ("hidden", "detached") and self._visible:
            raise TimeoutError("element never became hidden")

    def is_visible(self):
        return self._visible

    def inner_text(self):
        return self._text

    def input_value(self):
        return self._value


class _MobileElement:
    """Mimics a uiautomator2 element for assert handlers."""

    def __init__(self, *, exists=True, text=""):
        self._exists = exists
        self._text = text

    def wait(self, timeout=0):
        return self._exists

    def wait_gone(self, timeout=0):
        return not self._exists

    def get_text(self):
        return self._text


class _UrlDevice:
    """Mimics a Playwright page exposing the .url property (for assert_url)."""

    def __init__(self, url):
        self.url = url


class TestRefCache:
    """Ref cache is now bound to the UIExecutor instance, not a module global."""

    def _executor(self):
        return UIExecutor(object(), platform="web")

    def test_set_and_resolve(self, sample_ui_elements):
        ex = self._executor()
        ex.set_ui_elements(sample_ui_elements)
        el = ex.resolve_ref("@1")
        assert el is not None
        assert el["id"] == "submit-btn"

    def test_resolve_missing(self, sample_ui_elements):
        ex = self._executor()
        ex.set_ui_elements(sample_ui_elements)
        assert ex.resolve_ref("@999") is None

    def test_set_empty_clears(self, sample_ui_elements):
        ex = self._executor()
        ex.set_ui_elements(sample_ui_elements)
        ex.set_ui_elements([])
        assert ex.resolve_ref("@1") is None

    def test_two_executors_do_not_share_cache(self, sample_ui_elements):
        # The whole point of the refactor: separate instances are isolated.
        a = self._executor()
        b = self._executor()
        a.set_ui_elements(sample_ui_elements)
        assert a.resolve_ref("@1") is not None
        assert b.resolve_ref("@1") is None, "ref cache leaked across executor instances"


class TestLocatorBuilderBuildCode:
    def setup_method(self):
        # Ref resolution is now threaded as an explicit callable, not ambient
        # state. Build one over a known element list and pass it in.
        elements = [
            {"ref": "@1", "id": "btn-ok", "text": "OK", "x": 10, "y": 20, "w": 50, "h": 30},
            {"ref": "@2", "text": "Cancel", "x": 100, "y": 200, "w": 60, "h": 25},
            {"ref": "@3", "x": 50, "y": 50, "w": 40, "h": 20},
        ]
        self.resolve = lambda ref: next((e for e in elements if e["ref"] == ref), None)

    def test_ref_with_id(self):
        code = LocatorBuilder.build_code("web", "ref", "@1", resolve_ref=self.resolve)
        assert "#btn-ok" in code

    def test_ref_with_text_only(self):
        code = LocatorBuilder.build_code("web", "ref", "@2", resolve_ref=self.resolve)
        assert "get_by_text" in code
        assert "Cancel" in code

    def test_ref_with_no_attrs_never_emits_coordinate(self):
        # @3 has only x/y/w/h — no id/name/role/text. Under the coordinate-
        # honesty policy (P2), codegen must NOT bake a pixel click into a
        # persisted test; it emits a literal locator that fails loud instead.
        code = LocatorBuilder.build_code("web", "ref", "@3", resolve_ref=self.resolve)
        assert "mouse.click" not in code

    def test_ref_without_resolver_falls_back_to_literal(self):
        # No resolver (standalone codegen) → no element data → literal locator.
        code = LocatorBuilder.build_code("web", "ref", "@1")
        assert "@1" in code

    def test_css_id_locator(self):
        code = LocatorBuilder.build_code("web", "resourceId", "my-input")
        assert "#my-input" in code

    def test_text_locator(self):
        code = LocatorBuilder.build_code("web", "text", "Login")
        assert "get_by_text" in code
        assert "Login" in code

    def test_android_locator(self):
        code = LocatorBuilder.build_code("android", "text", "hello")
        assert code == "text='hello'"


class TestClickHandler:
    def test_generate_code_web(self):
        handler = ClickHandler()
        lines = handler.generate_code("web", "text", "Submit", "", 30.0)
        joined = "".join(lines)
        assert "allure.step" in joined
        assert "get_by_text('Submit')" in joined
        assert "click" in joined

    def test_generate_code_android(self):
        handler = ClickHandler()
        lines = handler.generate_code("android", "text", "OK", "", 30.0)
        joined = "".join(lines)
        assert "text='OK'" in joined
        assert ".click()" in joined


class TestInputHandler:
    def test_generate_code_web(self):
        handler = InputHandler()
        lines = handler.generate_code("web", "resourceId", "email", "user@test.com", 30.0)
        joined = "".join(lines)
        assert "#email" in joined
        assert "user@test.com" in joined
        assert "fill" in joined


class TestAssertExistExecute:
    """assert_exist.execute must return the real verdict, not always True (T4)."""

    def test_web_visible_passes(self):
        h = AssertExistHandler()
        assert h.execute(None, _WebElement(visible=True), "web", "") is True

    def test_web_not_visible_fails(self):
        h = AssertExistHandler()
        assert h.execute(None, _WebElement(visible=False), "web", "") is False

    def test_web_timeout_fails(self):
        h = AssertExistHandler()
        assert h.execute(None, _WebElement(raise_on_wait=True), "web", "") is False

    def test_mobile_exists_passes(self):
        h = AssertExistHandler()
        assert h.execute(None, _MobileElement(exists=True), "android", "") is True

    def test_mobile_missing_fails(self):
        h = AssertExistHandler()
        assert h.execute(None, _MobileElement(exists=False), "android", "") is False


class TestAssertTextEqualsExecute:
    """assert_text_equals.execute must fail on mismatch AND on read errors (T4)."""

    def test_web_match_passes(self):
        h = AssertTextEqualsHandler()
        assert h.execute(None, _WebElement(text="Welcome"), "web", "Welcome") is True

    def test_web_mismatch_fails(self):
        h = AssertTextEqualsHandler()
        assert h.execute(None, _WebElement(text="Bye"), "web", "Welcome") is False

    def test_web_read_error_fails(self):
        h = AssertTextEqualsHandler()
        assert h.execute(None, _WebElement(raise_on_wait=True), "web", "Welcome") is False

    def test_web_internal_whitespace_is_normalized(self):
        # The live verdict must match Playwright expect().to_have_text, which
        # collapses internal whitespace. "Hello   World" should equal
        # "Hello World" so the autonomous loop and the emitted test agree.
        h = AssertTextEqualsHandler()
        assert h.execute(None, _WebElement(text="Hello   World"), "web", "Hello World") is True
        assert h.execute(None, _WebElement(text="  Trimmed  "), "web", "Trimmed") is True

    def test_mobile_match_passes(self):
        h = AssertTextEqualsHandler()
        assert h.execute(None, _MobileElement(text="Welcome"), "android", "Welcome") is True

    def test_mobile_missing_fails(self):
        h = AssertTextEqualsHandler()
        assert h.execute(None, _MobileElement(exists=False), "android", "Welcome") is False


class TestAssertTextContainsExecute:
    """assert_text_contains: substring match, not exact equality."""

    def test_web_substring_passes(self):
        h = AssertTextContainsHandler()
        assert h.execute(None, _WebElement(text="Welcome back, Alice"), "web", "Welcome") is True

    def test_web_absent_substring_fails(self):
        h = AssertTextContainsHandler()
        assert h.execute(None, _WebElement(text="Goodbye"), "web", "Welcome") is False

    def test_web_read_error_fails(self):
        h = AssertTextContainsHandler()
        assert h.execute(None, _WebElement(raise_on_wait=True), "web", "Welcome") is False

    def test_mobile_substring_passes(self):
        h = AssertTextContainsHandler()
        assert h.execute(None, _MobileElement(text="Total: 42 items"), "android", "42") is True

    def test_mobile_missing_fails(self):
        h = AssertTextContainsHandler()
        assert h.execute(None, _MobileElement(exists=False), "android", "x") is False

    def test_generate_code_web_uses_expect_contain_text(self):
        code = "".join(AssertTextContainsHandler().generate_code("web", "text", "Greeting", "Hi", 30.0))
        assert "expect(" in code
        assert "to_contain_text('Hi'" in code

    def test_generate_code_android(self):
        code = "".join(AssertTextContainsHandler().generate_code("android", "text", "label", "42", 30.0))
        assert "in" in code
        assert "42" in code


class TestAssertNotExistExecute:
    """assert_not_exist: passes when the element is absent/hidden."""

    def test_web_absent_passes(self):
        h = AssertNotExistHandler()
        assert h.execute(None, _WebElement(visible=False), "web", "") is True

    def test_web_present_fails(self):
        h = AssertNotExistHandler()
        assert h.execute(None, _WebElement(visible=True), "web", "") is False

    def test_mobile_absent_passes(self):
        h = AssertNotExistHandler()
        assert h.execute(None, _MobileElement(exists=False), "android", "") is True

    def test_mobile_present_fails(self):
        h = AssertNotExistHandler()
        assert h.execute(None, _MobileElement(exists=True), "android", "") is False

    def test_generate_code_web_uses_expect_hidden(self):
        code = "".join(AssertNotExistHandler().generate_code("web", "text", "Spinner", "", 30.0))
        assert "expect(" in code
        assert "to_be_hidden" in code

    def test_web_requests_hidden_state_not_visible(self):
        # Guards against a wrong-state regression: assert_not_exist must wait on
        # state="hidden", not "visible". A bare boolean mock can't catch this;
        # recording last_state can.
        el = _WebElement(visible=False)
        AssertNotExistHandler().execute(None, el, "web", "")
        assert el.last_state == "hidden", f"expected wait_for(state='hidden'), got {el.last_state}"


class TestAssertValueExecute:
    """assert_value: checks an input/field's value (web input_value)."""

    def test_web_value_matches(self):
        h = AssertValueHandler()
        assert h.execute(None, _WebElement(value="admin"), "web", "admin") is True

    def test_web_value_mismatch_fails(self):
        h = AssertValueHandler()
        assert h.execute(None, _WebElement(value="root"), "web", "admin") is False

    def test_generate_code_web_uses_expect_value(self):
        code = "".join(AssertValueHandler().generate_code("web", "css", "#email", "a@b.com", 30.0))
        assert "expect(" in code
        assert "to_have_value('a@b.com'" in code


class TestAssertUrlExecute:
    """assert_url: global web assertion on page.url (substring match)."""

    def test_web_url_contains_passes(self):
        h = AssertUrlHandler()
        assert h.execute(_UrlDevice("https://x.com/dashboard?a=1"), None, "web", "/dashboard") is True

    def test_web_url_absent_fails(self):
        h = AssertUrlHandler()
        assert h.execute(_UrlDevice("https://x.com/login"), None, "web", "/dashboard") is False

    def test_generate_code_web_uses_expect_url(self):
        code = "".join(AssertUrlHandler().generate_code("web", "global", "global", "/dashboard", 30.0))
        assert "expect(" in code
        assert "to_have_url" in code


class TestWaitForExecute:
    """wait_for: explicit synchronization — wait until visible (default) or hidden."""

    def test_web_visible_passes(self):
        h = WaitForHandler()
        assert h.execute(None, _WebElement(visible=True), "web", "") is True

    def test_web_never_visible_fails(self):
        h = WaitForHandler()
        assert h.execute(None, _WebElement(visible=False), "web", "") is False

    def test_web_wait_hidden_passes(self):
        h = WaitForHandler()
        assert h.execute(None, _WebElement(visible=False), "web", "hidden") is True

    def test_mobile_appears_passes(self):
        h = WaitForHandler()
        assert h.execute(None, _MobileElement(exists=True), "android", "") is True

    def test_mobile_gone_passes(self):
        h = WaitForHandler()
        assert h.execute(None, _MobileElement(exists=False), "android", "hidden") is True

    def test_generate_code_web_visible(self):
        code = "".join(WaitForHandler().generate_code("web", "text", "Loaded", "", 30.0))
        assert "wait_for(state='visible'" in code

    def test_generate_code_web_hidden(self):
        code = "".join(WaitForHandler().generate_code("web", "text", "Spinner", "hidden", 30.0))
        assert "wait_for(state='hidden'" in code

    def test_web_execute_requests_correct_state(self):
        # Wrong-state regression guard at the execute() level (not just codegen).
        visible_el = _WebElement(visible=True)
        WaitForHandler().execute(None, visible_el, "web", "visible")
        assert visible_el.last_state == "visible"

        hidden_el = _WebElement(visible=False)
        WaitForHandler().execute(None, hidden_el, "web", "hidden")
        assert hidden_el.last_state == "hidden"


class TestNoMagicSleepInGeneratedGlobalActions:
    """Generated goto/swipe/press must NOT bake in fixed wait_for_timeout sleeps —
    those are the magic-sleep flakiness source. Web goto should wait on load
    state; nothing should emit a hardcoded wait_for_timeout."""

    def test_goto_has_no_magic_sleep(self):
        from common.executor import GotoHandler
        code = "".join(GotoHandler().generate_code("web", "global", "global", "example.com", 30.0))
        assert "wait_for_timeout" not in code, "goto still emits a magic sleep"
        # goto itself synchronizes via wait_until='load'; no networkidle
        # (Playwright discourages it) and no trailing sleep — the next action's
        # locator auto-waits.
        assert "wait_until='load'" in code
        assert "networkidle" not in code

    def test_press_web_has_no_magic_sleep(self):
        from common.executor import PressHandler
        code = "".join(PressHandler().generate_code("web", "global", "global", "Enter", 30.0))
        assert "wait_for_timeout" not in code, "press still emits a magic sleep"

    def test_swipe_web_has_no_magic_sleep(self):
        code = "".join(SwipeHandler().generate_code("web", "global", "global", "down", 30.0))
        assert "wait_for_timeout" not in code, "swipe still emits a magic sleep"


class TestNoUnusedPytestImportInHeader:
    """The generated file header must not carry an unused `import pytest` (F401):
    no handler references pytest, so shipping it makes every generated file
    lint-dirty (ruff selects F in pyproject)."""

    def test_header_has_no_unused_pytest_import(self):
        from cli.shared import get_initial_header
        header = "".join(get_initial_header())
        assert "import pytest" not in header


class _AssertDevice:
    """Device whose lookup returns a configurable mobile element."""

    def __init__(self, element):
        self._element = element

    def __call__(self, **kwargs):
        return self._element


class _FalsyMobileElement:
    """Mimics uiautomator2's UiObject: FALSY when it matches 0 elements (its
    __len__ returns the match count), yet a valid, non-None resolved handle.

    This is the shape that caused the android assert bug: execute_and_record
    gated on `element` truthiness, so a present-but-zero-match handle made the
    handler (and its wait) get skipped, wrongly reporting success.
    """

    def __init__(self, count=0, exists=False):
        self._count = count
        self._exists = exists

    def __len__(self):
        return self._count  # 0 -> falsy

    @property
    def exists(self):
        return self._exists

    def wait(self, timeout=0):
        return self._exists


class TestExecuteAndRecordAssertionTag:
    """execute_and_record must tag assertion failures so --json can disambiguate."""

    def test_failed_assert_sets_assertion_failed_flag(self):
        device = _AssertDevice(_MobileElement(exists=False))
        executor = UIExecutor(device, platform="android")
        result = executor.execute_and_record(
            {
                "action": "assert_exist",
                "locator_type": "text",
                "locator_value": "Dashboard",
                "extra_value": "",
            }
        )
        assert result["success"] is False
        assert result.get("assertion_failed") is True

    def test_passing_assert_succeeds_without_flag(self):
        device = _AssertDevice(_MobileElement(exists=True))
        executor = UIExecutor(device, platform="android")
        result = executor.execute_and_record(
            {
                "action": "assert_exist",
                "locator_type": "text",
                "locator_value": "Dashboard",
                "extra_value": "",
            }
        )
        assert result["success"] is True
        assert result.get("assertion_failed") is None

    def test_non_assert_failure_not_tagged_as_assertion(self):
        # A click whose element wait fails is an engine error, not assertion_failed.
        device = _AssertDevice(_MobileElement(exists=False))
        executor = UIExecutor(device, platform="android")
        result = executor.execute_and_record(
            {
                "action": "click",
                "locator_type": "text",
                "locator_value": "Login",
                "extra_value": "",
            }
        )
        assert result["success"] is False
        assert result.get("assertion_failed") is None

    def test_falsy_but_resolved_android_element_runs_handler(self):
        # Regression (found on a real device): a resolved-but-zero-match android
        # UiObject is FALSY. execute_and_record must still run the handler
        # (gating on `element is not None`, not truthiness) so the assert reports
        # a real failure instead of falling through to a fast false success.
        device = _AssertDevice(_FalsyMobileElement(count=0, exists=False))
        executor = UIExecutor(device, platform="android")
        result = executor.execute_and_record(
            {
                "action": "assert_exist",
                "locator_type": "text",
                "locator_value": "definitely-absent",
                "extra_value": "",
            }
        )
        assert result["success"] is False, "falsy android element wrongly reported success"
        assert result.get("assertion_failed") is True


class TestErrorCodeBubbling:
    """execute_and_record must surface a machine-readable error_code on the
    failure paths an agent hits, so the --action --json layer can diagnose
    without re-parsing stderr. The device-free early returns (E031/E035) are
    unit tested here; locate/action-time codes (E033/E037/E038) need a real
    page and are covered by the live suite and the diagnoser's own tests.
    """

    def _executor(self):
        from common.executor import UIExecutor

        return UIExecutor(object(), platform="web")

    def test_unsupported_action_bubbles_e031(self):
        ex = self._executor()
        result = ex.execute_and_record({"action": "teleport"})
        assert result["success"] is False
        assert result["error_code"] == "E031"

    def test_empty_action_bubbles_e035(self):
        ex = self._executor()
        result = ex.execute_and_record({"action": ""})
        assert result["success"] is False
        assert result["error_code"] == "E035"

    def test_failure_result_always_carries_error_code_key(self):
        # Even on the empty-action early return, the key is present (defaulted
        # to "" in the initializer, set to a real code on failure) so the
        # --action --json layer can read result["error_code"] unconditionally.
        ex = self._executor()
        result = ex.execute_and_record({"action": ""})
        assert "error_code" in result
        assert result["error_code"] == "E035"
