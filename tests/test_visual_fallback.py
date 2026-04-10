"""Tests for common/visual_fallback.py — VLM coordinate parsing."""

from unittest.mock import MagicMock, patch

from common.visual_fallback import visual_locate


def _mock_openai_response(content: str):
    """Create a mock OpenAI client returning the given content."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


class TestVisualLocate:
    @patch("openai.OpenAI")
    def test_json_response(self, mock_openai_cls):
        mock_openai_cls.return_value = _mock_openai_response('{"x": 150, "y": 300}')
        result = visual_locate(b"fake_png", "text=Submit")
        assert result == (150, 300)

    @patch("openai.OpenAI")
    def test_markdown_wrapped_json(self, mock_openai_cls):
        mock_openai_cls.return_value = _mock_openai_response('```json\n{"x": 42, "y": 99}\n```')
        result = visual_locate(b"fake_png", "text=Login")
        assert result == (42, 99)

    @patch("openai.OpenAI")
    def test_negative_coords_returns_none(self, mock_openai_cls):
        mock_openai_cls.return_value = _mock_openai_response('{"x": -1, "y": -1}')
        result = visual_locate(b"fake_png", "text=Missing")
        assert result is None

    @patch("openai.OpenAI")
    def test_api_error_returns_none(self, mock_openai_cls):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("timeout")
        mock_openai_cls.return_value = client
        result = visual_locate(b"fake_png", "text=Broken")
        assert result is None
