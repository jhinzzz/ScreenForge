"""ReviewRecorder：纯内存收集 pytest 回放的逐操作记录，无浏览器。

字段名刻意复用 PlaygroundStepEvent（cli/playground_sink.py:32-46）以留收敛门，
并增补 type/timestamp/code_loc/screenshot/dom_tree/error 等后续方向所需字段。
"""

from review.recorder import (
    ReviewRecorder,
    StepRecord,
    get_recorder,
    reset_recorder,
)


def test_steprecord_defaults_are_action_type():
    r = StepRecord(step_index=1, action="click")
    assert r.type == "action"          # ⭐留口：以后 heal/cache_hit/retry 不改 schema
    assert r.success is True
    assert r.dom_tree is None
    assert r.error is None


def test_recorder_collects_in_order():
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    rec.add(StepRecord(step_index=1, action="goto", action_description="Navigate"))
    rec.add(StepRecord(step_index=2, action="click", action_description="Click: Login"))
    assert [s.step_index for s in rec.records] == [1, 2]
    assert rec.run_id == "r1"
    assert rec.platform == "web"


def test_to_dict_shape():
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py", created_at=1751253600.0)
    rec.add(StepRecord(step_index=1, action="click", code_line="d.locator('#x').first.click()",
                       code_loc="t.py:18", screenshot="screenshots/step_001.png"))
    d = rec.to_dict()
    assert d["run_id"] == "r1"
    assert d["platform"] == "web"
    assert d["created_at"] == 1751253600.0
    assert d["test_file"] == "t.py"
    assert d["video"] is None
    assert d["cases"] == []          # 无归属信息 → 空，viewer 退化为单条时间轴
    assert len(d["steps"]) == 1
    assert d["steps"][0]["code_loc"] == "t.py:18"
    assert d["steps"][0]["screenshot"] == "screenshots/step_001.png"


def test_to_dict_excludes_thumbs_when_asked():
    # review.json 数据产物路径剔除 base64 缩略图；HTML 路径保留。
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    rec.add(StepRecord(step_index=1, action="click",
                       screenshot_thumb_b64="data:image/jpeg;base64,AAAA"))
    assert "screenshot_thumb_b64" in rec.to_dict()["steps"][0]
    assert "screenshot_thumb_b64" not in rec.to_dict(include_thumbs=False)["steps"][0]


def test_module_singleton_reset():
    reset_recorder()
    a = get_recorder()
    a.add(StepRecord(step_index=1, action="click"))
    assert len(get_recorder().records) == 1   # 同一实例
    reset_recorder()
    assert len(get_recorder().records) == 0    # reset 后是新实例
