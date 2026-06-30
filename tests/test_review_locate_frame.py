"""locate_test_frame：在调用栈里找到 test_*.py 那一帧，抽出 行号+源码。

用真实嵌套函数构造栈（模拟「测试 → patch 层 wrapper → 定位器」），断言它跳过
非 test_ 帧、命中 test_ 帧。文件名以 test_ 开头即视为测试帧。
"""

from review.recorder import locate_test_frame


def test_locates_calling_test_frame():
    # 本测试文件名以 test_ 开头 —— 直接调用应定位到本行所在帧。
    code_loc, code_line = locate_test_frame()
    assert code_loc.startswith("test_review_locate_frame.py:")
    assert "locate_test_frame()" in code_line


def test_skips_wrapper_frames_via_skip_files():
    # 模拟 patch 层 wrapper：一个住在「非 test_」文件里的中间函数调用定位器。
    # 这里用本文件模拟，但把本文件名加入 skip → 应跳过本帧、向上找不到 test_ 帧 → 空。
    def fake_wrapper():
        return locate_test_frame(skip_files=("test_review_locate_frame.py",))
    code_loc, code_line = fake_wrapper()
    assert code_loc == "" and code_line == ""


def test_returns_empty_when_no_test_frame(monkeypatch):
    # 不在任何 test_ 文件里调用时（理论上极少），优雅返回空而不抛。
    import review.recorder as rec
    # 直接验证契约：skip 掉当前文件即无 test_ 帧可用。
    assert rec.locate_test_frame(skip_files=("test_review_locate_frame.py",)) == ("", "")
