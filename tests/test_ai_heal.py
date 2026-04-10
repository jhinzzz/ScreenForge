"""Tests for common/ai_heal.py — HealResult parsing and validation."""

from common.ai_heal import HealResult, _parse_heal_response


class TestParseHealResponse:
    def test_valid_json(self):
        raw = '{"confidence": 0.9, "fix_description": "fixed locator", "fixed_code": "import pytest\\ndef test_a(): pass"}'
        r = _parse_heal_response(raw)
        assert r.confidence == 0.9
        assert r.fix_description == "fixed locator"
        assert "def test_a" in r.fixed_code

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"confidence": 0.8, "fix_description": "updated selector", "fixed_code": "def test_b(): pass"}\n```'
        r = _parse_heal_response(raw)
        assert r.confidence == 0.8
        assert "def test_b" in r.fixed_code

    def test_python_block_fallback(self):
        raw = "Here is the fix:\n```python\nimport pytest\ndef test_c(): assert True\n```"
        r = _parse_heal_response(raw)
        assert r.confidence == 0.3
        assert "def test_c" in r.fixed_code

    def test_unparseable_returns_zero_confidence(self):
        r = _parse_heal_response("I don't know how to fix this")
        assert r.confidence == 0.0
        assert r.fixed_code == ""

    def test_syntax_error_detected(self):
        r = HealResult(confidence=0.9, fix_description="test", fixed_code="def (broken")
        assert r.is_valid_syntax is False

    def test_valid_syntax_detected(self):
        r = HealResult(confidence=0.9, fix_description="test", fixed_code="def test_x(): pass")
        assert r.is_valid_syntax is True


class TestHealResultDataclass:
    def test_fields(self):
        r = HealResult(confidence=0.75, fix_description="desc", fixed_code="x = 1")
        assert r.confidence == 0.75
        assert r.fix_description == "desc"
        assert r.fixed_code == "x = 1"
