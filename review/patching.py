"""捕获层：对 Playwright Locator/Page 的操作方法做类级 monkeypatch。

为何不用代理对象：conftest.py:230 的 `d` 是 Playwright Page，不是 adapter。
代理对象会让 conftest.py:252 的 `__class__.__name__ == "Page"` 判定失败 → 平台误判
→ self-heal 崩在 dump_hierarchy()。类级 patch 保留真 Page，isinstance/类名都正常，
且链式调用 d.locator(x).first.click() 的 .click 天然命中 Locator.click 补丁。
"""

import functools
import time

from loguru import logger as log

from playground.dom_capture import build_web_tree
from review.recorder import StepRecord, get_recorder, locate_test_frame


def _build_web_table() -> list:
    from playwright.sync_api import Locator, Page
    locator_actions = [
        "click", "dblclick", "fill", "type", "press", "check", "uncheck",
        "select_option", "hover", "set_input_files", "tap", "drag_to",
    ]
    table = [(Locator, name) for name in locator_actions if hasattr(Locator, name)]
    if hasattr(Page, "goto"):
        table.append((Page, "goto"))
    return table


# 平台 → [(类, 方法名)]。web 填真值；移动端留文档化 stub（本次不验证）。
# 只 patch Locator 元素操作 + Page.goto；不 patch Page.click/fill 快捷方式（会双计）。
# 移动端 stub（接口就位，本次不实现 —— 见 spec §8）：
# "android": [(uiautomator2.UiObject, "click"), ...],
# "ios": [(wda.Element, "tap"), ...],
PLATFORM_PATCH_TABLE: dict = {}  # install_capture 时按平台惰性填充 web 表

# 保存被 patch 的原始方法，uninstall 时还原。
_ORIGINALS: list = []


def _resolve_page(receiver):
    """从被 patch 的接收者拿 Playwright Page：Page 自身，或 Locator.page。"""
    if hasattr(receiver, "screenshot") and hasattr(receiver, "goto"):
        return receiver                      # 是 Page
    return getattr(receiver, "page", None)   # 是 Locator


def _persist_screenshot(page, step_index: int) -> tuple:
    """抓全分辨 PNG → 返回 (相对路径, 缩略图b64)。在 Task 6 接真实现；
    此处给一个 import-safe 的占位，单测会 monkeypatch 它。"""
    return "", ""


def _record_after(receiver, method_name: str, exc, *, action: str) -> None:
    """一个操作执行后（成功或异常）记一条 StepRecord。绝不因记录失败而影响被测操作。"""
    try:
        recorder = get_recorder()
        idx = recorder.next_index()
        page = _resolve_page(receiver)
        screenshot_rel, thumb_b64 = ("", "")
        dom_tree = None
        if page is not None and exc is None:
            try:
                screenshot_rel, thumb_b64 = _persist_screenshot(page, idx)
            except Exception as e:
                log.debug(f"[review] screenshot skip: {e}")
            try:
                dom_tree = build_web_tree(page)
            except Exception as e:
                log.debug(f"[review] dom tree skip: {e}")
        code_loc, code_line = locate_test_frame()
        recorder.add(StepRecord(
            step_index=idx,
            timestamp=time.time(),
            action=action,
            action_description=f"{action}",
            code_line=code_line,
            code_loc=code_loc,
            success=exc is None,
            screenshot=screenshot_rel,
            screenshot_thumb_b64=thumb_b64,
            dom_tree=dom_tree,
            error=(f"{type(exc).__name__}: {exc}" if exc is not None else None),
        ))
    except Exception as e:  # 记录层绝不影响被测操作
        log.debug(f"[review] record skip: {e}")


def _wrap(cls, method_name: str):
    original = getattr(cls, method_name)

    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        try:
            result = original(self, *args, **kwargs)
        except Exception as exc:
            _record_after(self, method_name, exc, action=method_name)
            raise                       # ★ re-raise：pytest 退出码契约不变
        _record_after(self, method_name, None, action=method_name)
        return result

    _ORIGINALS.append((cls, method_name, original))
    setattr(cls, method_name, wrapper)


def install_capture(platform: str) -> None:
    """按平台安装类级 patch。web 表惰性构建（避免无浏览器环境 import 失败）。"""
    if platform == "web" and "web" not in PLATFORM_PATCH_TABLE:
        try:
            PLATFORM_PATCH_TABLE["web"] = _build_web_table()
        except Exception as e:
            log.warning(f"[review] cannot build web patch table: {e}")
            return
    for cls, method_name in PLATFORM_PATCH_TABLE.get(platform, []):
        _wrap(cls, method_name)
    log.info(f"[review] capture installed for {platform} ({len(_ORIGINALS)} methods)")


def uninstall_capture() -> None:
    while _ORIGINALS:
        cls, method_name, original = _ORIGINALS.pop()
        setattr(cls, method_name, original)
