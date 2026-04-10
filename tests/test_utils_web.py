"""Tests for utils/utils_web.py — DOM compression and URL normalization."""

import json
from unittest.mock import MagicMock

from utils.utils_web import compress_web_dom, normalize_loopback_url


class TestNormalizeLoopbackUrl:
    def test_localhost_replaced(self):
        assert normalize_loopback_url("http://localhost:3000/app") == "http://127.0.0.1:3000/app"

    def test_non_localhost_unchanged(self):
        url = "https://example.com/path?q=1"
        assert normalize_loopback_url(url) == url

    def test_localhost_no_port(self):
        assert normalize_loopback_url("http://localhost/") == "http://127.0.0.1/"


class TestCompressWebDom:
    def test_returns_json_with_ui_elements(self):
        mock_page = MagicMock()
        mock_page.evaluate.return_value = '{"ui_elements": [{"ref": "@1", "class": "button"}]}'

        result = compress_web_dom(mock_page)
        data = json.loads(result)
        assert "ui_elements" in data
        assert len(data["ui_elements"]) == 1
        assert data["ui_elements"][0]["ref"] == "@1"

    def test_returns_empty_on_exception(self):
        mock_page = MagicMock()
        mock_page.evaluate.side_effect = Exception("disconnected")

        result = compress_web_dom(mock_page)
        data = json.loads(result)
        assert data == {"ui_elements": []}
