"""Forward candidate ranking: a plain-language phrase -> usable locators.

Same ranking that powers post-failure did-you-mean, but called BEFORE acting:
the agent says what it wants in words and gets ranked elements back. Literal
similarity only (difflib) — see the ceiling test at the bottom.
"""

from common.failure_diagnosis import rank_candidates


def _page():
    return [
        {"class": "Button", "text": "登录", "id": "com.app:id/login"},
        {"class": "Button", "text": "注册", "id": "com.app:id/reg"},
        {"class": "TextView", "text": "忘记密码", "id": "com.app:id/forgot"},
    ]


def test_returns_plain_dicts_not_dataclasses():
    out = rank_candidates("登录", _page())
    assert isinstance(out, list)
    assert isinstance(out[0], dict)
    assert set(out[0]) == {"text", "score", "locator"}


def test_ranks_the_best_match_first():
    out = rank_candidates("登录", _page())
    assert out[0]["text"] == "登录"
    assert out[0]["locator"] == {"type": "resourceId", "value": "com.app:id/login"}


def test_empty_phrase_returns_empty():
    assert rank_candidates("", _page()) == []


def test_empty_page_returns_empty():
    assert rank_candidates("登录", []) == []


def test_below_threshold_returns_nothing_rather_than_guessing():
    # Invariant 2 / the module's honesty contract: no plausible-looking guess.
    assert rank_candidates("完全无关的词句", _page()) == []


def test_caps_at_three_candidates():
    page = [{"class": "Button", "text": f"登录{i}", "id": f"id{i}"} for i in range(10)]
    assert len(rank_candidates("登录", page)) <= 3


def test_scores_are_json_safe_floats():
    out = rank_candidates("登录", _page())
    assert all(isinstance(c["score"], float) for c in out)


def test_known_ceiling_literal_not_semantic():
    # difflib is literal similarity. A Chinese phrase against English labels
    # scores near zero, so the field is EMPTY on mixed-language pages. This is
    # the documented ceiling, pinned so nobody "fixes" it by lowering the
    # threshold (which would trade honesty for noise).
    english_page = [{"class": "button", "text": "Sign in", "ref": "@1"}]
    assert rank_candidates("登录", english_page) == []
