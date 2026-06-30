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
        # 锚定 "/token" 而非裸子串：否则 skip 项 "recorder.py" 会误命中
        # 合法测试文件 test_recorder.py。"/{s}" 命中路径组件，s == base 兜底裸 basename。
        # 注：/{s} 仅匹配 POSIX 路径分隔符（本仓库 macOS/Linux）；s == base 兜底跨平台生效。
        if any(f"/{s}" in filename or s == base for s in skip):
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
    test: str = ""                # 所属用例 nodeid（多用例报告分组用；空=未归属/旧数据）
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
        self.out_dir: str = ""   # 报告输出目录（截图落这里的 screenshots/ 子目录）
        self.current_test: str = ""   # 当前正在跑的用例 nodeid（捕获层据此给 step 打标）
        # nodeid -> {"outcome","duration","error"}：来自 pytest 的权威判定（非由 step 推断）。
        self.case_results: dict[str, dict] = {}

    def start_run(self, run_id: str, platform: str, test_file: str,
                  created_at: float = 0.0, out_dir: str = "") -> None:
        self.run_id = run_id
        self.platform = platform
        self.test_file = test_file
        self.created_at = created_at
        self.out_dir = out_dir

    def add(self, record: StepRecord) -> None:
        if not record.test and self.current_test:
            record.test = self.current_test
        self.records.append(record)

    def record_case_result(self, nodeid: str, outcome: str,
                           duration: float = 0.0, error: Optional[str] = None) -> None:
        """登记一个用例的权威判定（来自 pytest makereport，非由 step 推断）。

        失败优先：一个 nodeid 多次上报时（如 setup pass + call fail），fail 不被覆盖。
        """
        prev = self.case_results.get(nodeid)
        if prev and prev.get("outcome") == "failed" and outcome != "failed":
            return
        self.case_results[nodeid] = {
            "outcome": outcome, "duration": duration, "error": error,
        }

    def next_index(self) -> int:
        """下一个 1-based step_index（捕获层用）。"""
        return len(self.records) + 1

    def to_dict(self, include_thumbs: bool = True) -> dict:
        """include_thumbs=False 时剔除 screenshot_thumb_b64（仅 HTML 胶片需要内嵌缩略图，
        review.json 作为数据产物不应被每步 base64 撑爆 —— 见 review.json 用途说明）。"""
        exclude = None if include_thumbs else {"screenshot_thumb_b64"}
        return {
            "run_id": self.run_id,
            "platform": self.platform,
            "created_at": self.created_at,
            "test_file": self.test_file,
            "video": self.video,
            "cases": self._build_cases(),
            "steps": [r.model_dump(exclude=exclude) for r in self.records],
        }

    def _build_cases(self) -> list[dict]:
        """按出现顺序聚合用例：step 区间 + pytest 权威判定。无任何归属信息则返回 []。

        viewer 据此分组；cases 为空时 viewer 退化为单条 session 时间轴（向后兼容旧数据）。
        """
        order: list[str] = []
        spans: dict[str, list[int]] = {}
        for r in self.records:
            nid = r.test
            if not nid:
                continue
            if nid not in spans:
                order.append(nid)
                spans[nid] = [r.step_index, r.step_index]
            else:
                spans[nid][1] = r.step_index
        # 有判定但无 step 的用例（如断言阶段失败、未触发任何被 patch 操作）也要present。
        for nid in self.case_results:
            if nid not in spans:
                order.append(nid)
                spans[nid] = [0, 0]
        cases = []
        for nid in order:
            res = self.case_results.get(nid, {})
            lo, hi = spans[nid]
            cases.append({
                "nodeid": nid,
                "name": nid.split("::")[-1] if "::" in nid else nid,
                "outcome": res.get("outcome", "unknown"),
                "duration": res.get("duration", 0.0),
                "error": res.get("error"),
                "step_from": lo,
                "step_to": hi,
            })
        return cases


_RECORDER = ReviewRecorder()


def get_recorder() -> ReviewRecorder:
    return _RECORDER


def reset_recorder() -> None:
    global _RECORDER
    _RECORDER = ReviewRecorder()
