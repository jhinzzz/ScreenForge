"""pytest 回放 Review 报告 —— 纯内存收集层。

捕获层（review/patching.py）在每个非断言操作后调 get_recorder().add(...)；
pytest_sessionfinish 读 to_dict() 渲染报告。本模块零浏览器依赖、纯数据，便于单测。
字段名复用 PlaygroundStepEvent（cli/playground_sink.py:32-46）以留 viewer 收敛门。
"""

import inspect
import linecache
import os
from typing import Optional

from pydantic import BaseModel

# 框架/本层帧的 basename 特征：定位测试行时跳过它们。
_FRAME_SKIP_DEFAULT = ("recorder.py", "patching.py", "_pytest", "allure", "site-packages")


def locate_test_frame(skip_files: tuple[str, ...] = ()) -> tuple[str, str]:
    """上溯调用栈，返回第一个测试帧的 (code_loc, code_line)，定位不到则 ("", "")。

    判定测试帧：basename 以 'test_' 开头，且不在 skip 名单里。按文件名特征过滤
    （而非固定栈深偏移），以容忍 allure.step 等上下文管理器插入的额外帧。
    """
    skip = tuple(skip_files) + _FRAME_SKIP_DEFAULT
    for frame_info in inspect.stack():
        filename = frame_info.filename
        base = os.path.basename(filename)
        if any(s in filename or s == base for s in skip):
            continue
        if base.startswith("test_"):
            lineno = frame_info.lineno
            src = linecache.getline(filename, lineno).strip()
            return f"{base}:{lineno}", src
    return "", ""


class StepRecord(BaseModel):
    """一个非断言操作的记录。字段名与 PlaygroundStepEvent 重叠者保持一致。"""

    step_index: int
    type: str = "action"          # ⭐留口：action|heal|cache_hit|retry（以后加值不改 schema）
    timestamp: float = 0.0        # ⭐留口：连续视频同步用（time.time()）
    action: str = ""              # 复用 PlaygroundStepEvent
    action_description: str = ""  # 复用
    code_line: str = ""           # 触发该操作的测试源码行
    code_loc: str = ""            # "test_x.py:18"；定位失败则空（诚实降级）
    success: bool = True
    screenshot: str = ""          # 相对路径（不破链），如 "screenshots/step_001.png"
    screenshot_thumb_b64: str = ""  # 缩略图内嵌（data:image/jpeg;base64,...）
    dom_tree: Optional[dict] = None  # build_web_tree 输出；None = 该步无树（诚实）
    error: Optional[str] = None      # 失败步的异常摘要


class ReviewRecorder:
    """单次 pytest session 的逐操作收集器。"""

    def __init__(self) -> None:
        self.run_id: str = ""
        self.platform: str = ""
        self.test_file: str = ""
        self.created_at: float = 0.0
        self.video: Optional[str] = None
        self.records: list[StepRecord] = []

    def start_run(self, run_id: str, platform: str, test_file: str,
                  created_at: float = 0.0) -> None:
        self.run_id = run_id
        self.platform = platform
        self.test_file = test_file
        self.created_at = created_at

    def add(self, record: StepRecord) -> None:
        self.records.append(record)

    def next_index(self) -> int:
        """下一个 1-based step_index（捕获层用）。"""
        return len(self.records) + 1

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "platform": self.platform,
            "created_at": self.created_at,
            "test_file": self.test_file,
            "video": self.video,
            "steps": [r.model_dump() for r in self.records],
        }


_RECORDER = ReviewRecorder()


def get_recorder() -> ReviewRecorder:
    return _RECORDER


def reset_recorder() -> None:
    global _RECORDER
    _RECORDER = ReviewRecorder()
