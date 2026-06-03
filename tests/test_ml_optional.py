"""MF1 guard: the core install must not require the ML stack.

torch / transformers / sentence-transformers (~2GB) power the OPTIONAL semantic
cache only and live in the `[ml]` extra, not core requirements. The bug this
pins: sentence_transformers was imported at module top in embedding_loader.py,
and cache_manager imported the loader eagerly, so a clean (core-only) install
crashed at `import common.ai` — before any graceful-degrade code could run.

These tests simulate the package being absent and assert import + cache use
degrade instead of crashing. (In CI the package IS installed, so we block it
via an import hook for the duration of the test.)
"""

import builtins
import importlib
import sys
import tempfile

import pytest


@pytest.fixture
def no_sentence_transformers(monkeypatch):
    """Make `import sentence_transformers` raise ModuleNotFoundError, and drop any
    cached copy + the cache modules so they re-import under the block."""
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    for mod in list(sys.modules):
        if mod.startswith("sentence_transformers"):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr(builtins, "__import__", blocked)
    yield


def test_import_ai_surface_without_ml(no_sentence_transformers):
    # Re-import the cache + ai modules fresh under the block.
    for mod in ("common.ai", "common.cache", "common.cache.cache_manager",
                "common.cache.embedding_loader"):
        sys.modules.pop(mod, None)
    # Must not raise ModuleNotFoundError.
    importlib.import_module("common.cache")
    importlib.import_module("common.ai")


def test_cache_degrades_to_exact_key_without_ml(no_sentence_transformers):
    sys.modules.pop("common.cache.embedding_loader", None)
    sys.modules.pop("common.cache.cache_manager", None)
    sys.modules.pop("common.cache", None)
    from common.cache import CacheManager

    cm = CacheManager(cache_dir=tempfile.mkdtemp(), enabled=True)

    # Semantic lookup degrades to miss (no embeddings), no crash.
    assert cm.get("点击登录", {"ui_elements": []}, "android") is None
    # Exact-key write still succeeds and is retrievable (hash-based, no vectors).
    assert cm.set("点击登录", {"ui_elements": []}, {"action": "click"}, "android") is True
    assert cm.get("点击登录", {"ui_elements": []}, "android") == {"action": "click"}


def test_embedding_returns_none_without_ml(no_sentence_transformers):
    sys.modules.pop("common.cache.embedding_loader", None)
    sys.modules.pop("common.cache.cache_manager", None)
    sys.modules.pop("common.cache", None)
    from common.cache import CacheManager

    cm = CacheManager(cache_dir=tempfile.mkdtemp(), enabled=True)
    assert cm._get_embedding("anything") is None
