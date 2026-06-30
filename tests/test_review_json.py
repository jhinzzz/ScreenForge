import json

from review.recorder import ReviewRecorder, StepRecord
from review.render import write_review_json


def test_write_review_json_roundtrip(tmp_path):
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py", created_at=1.0)
    rec.add(StepRecord(step_index=1, action="click", code_loc="t.py:18",
                       screenshot="screenshots/step_001.png"))
    path = write_review_json(rec, tmp_path)
    assert path == tmp_path / "review.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "r1"
    assert data["steps"][0]["action"] == "click"
    assert data["steps"][0]["screenshot"] == "screenshots/step_001.png"


def test_write_review_json_keeps_cjk_literal(tmp_path):
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    rec.add(StepRecord(step_index=1, action="click", action_description="点击登录"))
    path = write_review_json(rec, tmp_path)
    raw = path.read_text(encoding="utf-8")
    assert "点击登录" in raw   # 字面 UTF-8，非 \u 转义
