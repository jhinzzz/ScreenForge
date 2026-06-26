"""Tests for common/cache/cache_hash.py — the cache KEY builder.

This is the highest-risk untested logic in the cache: a bug here produces a
wrong cache hit, which replays the *wrong* action against the page. These
tests pin the invariants the fingerprint relies on (determinism, immunity to
dynamic data / render order, the blocklist, and the Chinese-length window) and
the instruction-hash normalization.
"""

from common.cache.cache_hash import (
    _extract_semantic_fingerprint,
    compute_instruction_hash,
    compute_ui_hash,
)


def _page(*texts: str) -> dict:
    return {"ui_elements": [{"class": "Button", "text": t} for t in texts]}


def test_ui_hash_is_deterministic_for_same_skeleton():
    assert compute_ui_hash(_page("登录", "注册")) == compute_ui_hash(_page("登录", "注册"))


def test_ui_hash_ignores_element_order():
    # fingerprint is sorted before hashing → render-order shuffle must not matter
    assert compute_ui_hash(_page("登录", "注册")) == compute_ui_hash(_page("注册", "登录"))


def test_ui_hash_immune_to_dynamic_data():
    # The core promise: digits/symbols are stripped, so a price/balance/count that
    # changes between runs must NOT change the page skeleton hash.
    assert compute_ui_hash(_page("余额 100", "登录")) == compute_ui_hash(_page("余额 9999", "登录"))


def test_fingerprint_excludes_blocklisted_terms():
    # Blocklisted volatile labels are dropped entirely, so a page that differs
    # only by them collapses to the same fingerprint.
    fp = _extract_semantic_fingerprint(_page("比特币", "登录"))
    assert not any("比特币" in feature for feature in fp)
    assert any("登录" in feature for feature in fp)


def test_fingerprint_drops_text_outside_2_to_6_char_window():
    # 1 Chinese char (too short) and 7+ chars (too long) are not anchor-like → dropped.
    fp = _extract_semantic_fingerprint(_page("好", "这是一段非常长的描述文本", "登录"))
    assert fp == ["Button|登录"]


def test_instruction_hash_normalizes_whitespace_and_case():
    assert compute_instruction_hash("  Click  LOGIN ") == compute_instruction_hash("click login")
    assert compute_instruction_hash("点击 登录") != compute_instruction_hash("点击 注册")
