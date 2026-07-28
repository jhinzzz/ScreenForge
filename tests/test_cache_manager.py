"""Tests for common/cache/cache_manager.py — cache hit/miss/write logic."""

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


class TestCacheManagerTTLPruning:
    def test_write_prunes_expired_entries_from_disk(self, cache_manager, cache_dir):
        # Seed one entry, then age it past TTL on disk. A later write must not
        # re-persist the expired entry — the write path reloads+saves the whole
        # file, so without pruning it kept dead entries forever (unbounded growth).
        from common.cache.cache_storage import load_cache, save_cache

        cache_manager.set("old instruction", {"ui_elements": []}, {"action": "click"}, "web")

        data = load_cache(cache_dir)
        (old_key,) = list(data["entries"].keys())
        data["entries"][old_key]["metadata"]["created_at"] = "2000-01-01T00:00:00+00:00"
        save_cache(cache_dir, data)

        # A fresh write of an unrelated entry triggers the load+save cycle.
        cache_manager.set("new instruction", {"ui_elements": []}, {"action": "click"}, "web")

        remaining = load_cache(cache_dir)["entries"]
        assert old_key not in remaining, "expired entry was re-persisted on write"
        assert len(remaining) == 1


class TestCacheManagerSizeCap:
    def test_write_evicts_oldest_when_over_size_cap(self, cache_manager, cache_dir):
        # max_size_mb was accepted but never enforced — the cache grew unbounded
        # within the TTL window. With a tiny cap, writing many entries must evict
        # the least-recently-accessed ones and keep the newest.
        from common.cache.cache_storage import load_cache

        cache_manager._max_size_bytes = 5000  # ~2 entries fit (each carries a vector)
        for i in range(6):
            cache_manager.set_chat_simple(
                f"instruction {i}", {"action": "click", "locator_value": f"btn{i}"}, "web"
            )

        entries = load_cache(cache_dir)["entries"]
        assert len(entries) < 6, "cache grew unbounded — size cap not enforced"
        assert any(e.get("instruction") == "instruction 5" for e in entries.values())
        assert not any(e.get("instruction") == "instruction 0" for e in entries.values())


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
