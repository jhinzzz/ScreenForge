"""Tests for common/executor.py — ref cache, LocatorBuilder, handlers."""


from common.executor import (
    AssertExistHandler,
    AssertTextEqualsHandler,
    ClickHandler,
    InputHandler,
    LocatorBuilder,
    UIExecutor,
    _resolve_ref,
    set_ui_elements,
)


class _WebElement:
    """Mimics a Playwright locator for assert handlers."""

    def __init__(self, *, visible=True, text="", raise_on_wait=False):
        self._visible = visible
        self._text = text
        self._raise = raise_on_wait

    def wait_for(self, state="visible", timeout=0):
        if self._raise:
            raise TimeoutError("element not visible")

    def is_visible(self):
        return self._visible

    def inner_text(self):
        return self._text


class _MobileElement:
    """Mimics a uiautomator2 element for assert handlers."""

    def __init__(self, *, exists=True, text=""):
        self._exists = exists
        self._text = text

    def wait(self, timeout=0):
        return self._exists

    def get_text(self):
        return self._text


class TestRefCache:
    def test_set_and_resolve(self, sample_ui_elements):
        set_ui_elements(sample_ui_elements)
        el = _resolve_ref("@1")
        assert el is not None
        assert el["id"] == "submit-btn"

    def test_resolve_missing(self, sample_ui_elements):
        set_ui_elements(sample_ui_elements)
        assert _resolve_ref("@999") is None

    def test_set_empty_clears(self, sample_ui_elements):
        set_ui_elements(sample_ui_elements)
        set_ui_elements([])
        assert _resolve_ref("@1") is None


class TestLocatorBuilderBuildCode:
    def setup_method(self):
        set_ui_elements([
            {"ref": "@1", "id": "btn-ok", "text": "OK", "x": 10, "y": 20, "w": 50, "h": 30},
            {"ref": "@2", "text": "Cancel", "x": 100, "y": 200, "w": 60, "h": 25},
            {"ref": "@3", "x": 50, "y": 50, "w": 40, "h": 20},
        ])

    def test_ref_with_id(self):
        code = LocatorBuilder.build_code("web", "ref", "@1")
        assert "#btn-ok" in code

    def test_ref_with_text_only(self):
        code = LocatorBuilder.build_code("web", "ref", "@2")
        assert "get_by_text" in code
        assert "Cancel" in code

    def test_ref_coordinate_fallback(self):
        code = LocatorBuilder.build_code("web", "ref", "@3")
        assert "mouse.click" in code

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
        set_ui_elements([])
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
        set_ui_elements([])
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

    def test_mobile_match_passes(self):
        h = AssertTextEqualsHandler()
        assert h.execute(None, _MobileElement(text="Welcome"), "android", "Welcome") is True

    def test_mobile_missing_fails(self):
        h = AssertTextEqualsHandler()
        assert h.execute(None, _MobileElement(exists=False), "android", "Welcome") is False


class _AssertDevice:
    """Device whose lookup returns a configurable mobile element."""

    def __init__(self, element):
        self._element = element

    def __call__(self, **kwargs):
        return self._element


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
