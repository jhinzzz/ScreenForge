"""捕获层：类级 monkeypatch + 白名单 + 失败 re-raise。

不用真浏览器 —— 用假 Locator/Page 类验证：白名单方法被包裹后产生 StepRecord、
异常被记录且 re-raise、uninstall 后还原。真 Playwright 类的 patch 在 live smoke 验证。
"""

import pytest

from review import patching
from review.recorder import get_recorder, reset_recorder


class _FakeLocator:
    def __init__(self, page): self.page = page
    def click(self, *a, **k): return "clicked"
    def wait_for(self, *a, **k): return "waited"   # 断言类：不该被记录


class _FakePage:
    def screenshot(self): return b"\x89PNG_fake"
    def goto(self, url, *a, **k): return f"went:{url}"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    reset_recorder()
    # 把 DOM 抓取与截图持久化打桩，隔离纯 patch 逻辑。
    monkeypatch.setattr(patching, "build_web_tree", lambda page: {"platform": "web", "nodes": []})
    monkeypatch.setattr(patching, "_persist_screenshot", lambda page, idx: ("screenshots/step_%03d.png" % idx, ""))
    yield


def test_whitelisted_method_records(monkeypatch):
    monkeypatch.setattr(patching, "PLATFORM_PATCH_TABLE",
                        {"web": [(_FakeLocator, "click"), (_FakePage, "goto")]})
    patching.install_capture("web")
    try:
        page = _FakePage()
        loc = _FakeLocator(page)
        assert loc.click() == "clicked"          # 原行为保留
        assert page.goto("https://x") == "went:https://x"
    finally:
        patching.uninstall_capture()
    recs = get_recorder().records
    assert [r.action for r in recs] == ["click", "goto"]
    assert recs[0].success is True
    assert recs[0].dom_tree == {"platform": "web", "nodes": []}
    assert recs[0].screenshot == "screenshots/step_001.png"


def test_blacklisted_method_not_recorded(monkeypatch):
    # wait_for 不在 PLATFORM_PATCH_TABLE → 不被 patch → 不产生记录。
    monkeypatch.setattr(patching, "PLATFORM_PATCH_TABLE", {"web": [(_FakeLocator, "click")]})
    patching.install_capture("web")
    try:
        loc = _FakeLocator(_FakePage())
        loc.wait_for()
        loc.click()
    finally:
        patching.uninstall_capture()
    assert [r.action for r in get_recorder().records] == ["click"]


def test_exception_is_recorded_and_reraised(monkeypatch):
    class _BoomLocator:
        def __init__(self, page): self.page = page
        def click(self, *a, **k): raise RuntimeError("locator not found")
    monkeypatch.setattr(patching, "PLATFORM_PATCH_TABLE", {"web": [(_BoomLocator, "click")]})
    patching.install_capture("web")
    try:
        with pytest.raises(RuntimeError, match="locator not found"):
            _BoomLocator(_FakePage()).click()      # 必须 re-raise → pytest 照常失败
    finally:
        patching.uninstall_capture()
    recs = get_recorder().records
    assert len(recs) == 1
    assert recs[0].success is False
    assert "locator not found" in recs[0].error


def test_uninstall_restores_original(monkeypatch):
    monkeypatch.setattr(patching, "PLATFORM_PATCH_TABLE", {"web": [(_FakeLocator, "click")]})
    original = _FakeLocator.click
    patching.install_capture("web")
    assert _FakeLocator.click is not original
    patching.uninstall_capture()
    assert _FakeLocator.click is original
