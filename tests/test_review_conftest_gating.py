"""门控：默认 REVIEW_RECORD 未设时捕获层不挂；设了才录。

不真跑浏览器 —— 验证 conftest 暴露的 helper 的门控分支。
"""

import importlib


def test_review_enabled_helper(monkeypatch):
    import conftest
    importlib.reload(conftest)
    monkeypatch.delenv("REVIEW_RECORD", raising=False)
    assert conftest._review_enabled() is False
    monkeypatch.setenv("REVIEW_RECORD", "1")
    assert conftest._review_enabled() is True
    monkeypatch.setenv("REVIEW_RECORD", "0")
    assert conftest._review_enabled() is False


def test_review_run_id_shape(monkeypatch):
    import conftest
    rid = conftest._new_review_run_id()
    # 形如 20260630_104000_xxxxxxxx（mirror run_reporter.py:198）
    assert len(rid) >= 17 and "_" in rid
