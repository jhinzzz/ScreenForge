"""Tests for common/executor.py — ref cache, LocatorBuilder, handlers."""

from unittest.mock import MagicMock

from common.executor import (
    ClickHandler,
    InputHandler,
    LocatorBuilder,
    _resolve_ref,
    set_ui_elements,
)


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
