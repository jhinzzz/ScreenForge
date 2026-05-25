"""Tests for common/cache/cache_manager.py — cache hit/miss/write logic."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def cache_dir(tmp_path):
    return str(tmp_path / "cache")


@pytest.fixture
def cache_manager(cache_dir):
    with patch("common.cache.cache_manager.EmbeddingModelLoader") as mock_loader:
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=MagicMock(return_value=[0.1] * 384))
        mock_loader.return_value.load.return_value = mock_model

        from common.cache.cache_manager import CacheManager
        cm = CacheManager(cache_dir=cache_dir, enabled=True, ttl_days=1, max_size_mb=10)
        return cm


class TestCacheManagerSetAndGet:
    def test_set_then_get_l1(self, cache_manager):
        instruction = "click login button"
        ui = {"ui_elements": [{"text": "Login", "id": "btn"}]}
        decision = {"action": "click", "locator_type": "text", "locator_value": "Login"}

        result = cache_manager.set(instruction, ui, decision, "web", llm_latency=1.5)
        assert result is True

        cached = cache_manager.get(instruction, ui, "web")
        assert cached is not None
        assert cached["action"] == "click"

    def test_get_miss_returns_none(self, cache_manager):
        ui = {"ui_elements": []}
        cached = cache_manager.get("nonexistent instruction", ui, "web")
        assert cached is None

    def test_set_then_get_l2(self, cache_manager):
        instruction = "fill email field"
        decision = {"action": "input", "locator_type": "css", "locator_value": "#email"}

        result = cache_manager.set_chat_simple(instruction, decision, "web", llm_latency=2.0)
        assert result is True

        cached = cache_manager.get_chat_simple(instruction, "web")
        assert cached is not None
        assert cached["action"] == "input"

    def test_different_platform_miss(self, cache_manager):
        instruction = "click submit"
        ui = {"ui_elements": [{"text": "Submit"}]}
        decision = {"action": "click"}

        cache_manager.set(instruction, ui, decision, "web")
        cached = cache_manager.get(instruction, ui, "android")
        assert cached is None


class TestCacheManagerClear:
    def test_clear_removes_entries(self, cache_manager):
        instruction = "test"
        ui = {"ui_elements": []}
        decision = {"action": "click"}

        cache_manager.set(instruction, ui, decision, "web")
        cache_manager.clear()

        cached = cache_manager.get(instruction, ui, "web")
        assert cached is None


class TestCacheManagerStats:
    def test_stats_returns_dict(self, cache_manager):
        stats = cache_manager.get_stats()
        assert isinstance(stats, dict)


class TestCacheManagerDisabled:
    def test_disabled_cache_returns_none(self, cache_dir):
        with patch("common.cache.cache_manager.EmbeddingModelLoader"):
            from common.cache.cache_manager import CacheManager
            cm = CacheManager(cache_dir=cache_dir, enabled=False)

        ui = {"ui_elements": []}
        decision = {"action": "click"}
        cm.set("test", ui, decision, "web")

        cached = cm.get("test", ui, "web")
        assert cached is None
