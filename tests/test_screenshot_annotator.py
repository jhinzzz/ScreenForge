"""Tests for utils/screenshot_annotator.py — screenshot annotation."""

import io

from PIL import Image

from utils.screenshot_annotator import annotate_screenshot


def _make_png(width=400, height=300) -> bytes:
    """Create a minimal valid PNG image."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestAnnotateScreenshot:
    def test_returns_valid_png(self, sample_ui_elements):
        png = _make_png()
        result = annotate_screenshot(png, sample_ui_elements)

        # Result should be valid PNG
        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"
        assert img.size == (400, 300)

    def test_skips_non_clickable(self, sample_ui_elements):
        """Non-clickable elements (@3) should not get annotated."""
        png = _make_png()
        # Should not raise even with non-clickable elements
        result = annotate_screenshot(png, sample_ui_elements)
        assert len(result) > 0

    def test_skips_zero_size_elements(self, sample_ui_elements):
        """Elements with w=0 or h=0 (@4) should be skipped."""
        png = _make_png()
        # Should not raise
        result = annotate_screenshot(png, sample_ui_elements)
        assert len(result) > 0

    def test_empty_elements_list(self):
        """Empty element list should return an unmodified-size image."""
        png = _make_png(200, 100)
        result = annotate_screenshot(png, [])
        img = Image.open(io.BytesIO(result))
        assert img.size == (200, 100)
