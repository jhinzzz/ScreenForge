from review.recorder import ReviewRecorder, StepRecord
from review.render import render_html


def _rec():
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py", created_at=1.0)
    rec.add(StepRecord(step_index=1, action="goto", action_description="Navigate",
                       code_line="d.goto('https://x')", code_loc="t.py:10",
                       screenshot="screenshots/step_001.png",
                       screenshot_thumb_b64="data:image/jpeg;base64,AAAA",
                       dom_tree={"platform": "web", "nodes":
                                 [{"class": "button", "text": "Login", "ref": "@1",
                                   "x": 10, "y": 20, "w": 80, "h": 30, "children": []}]}))
    return rec


def test_render_html_inlines_data_and_is_selfcontained(tmp_path):
    path = render_html(_rec(), tmp_path)
    assert path == tmp_path / "report.html"
    html = path.read_text(encoding="utf-8")
    assert "const REVIEW" in html            # 数据已烘焙
    assert '"run_id": "r1"' in html or '"run_id":"r1"' in html
    assert "screenshots/step_001.png" in html  # 全分辨相对路径引用
    assert "data:image/jpeg;base64,AAAA" in html  # 缩略图内嵌
    assert "Navigate" in html


def test_render_html_keeps_cjk(tmp_path):
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    rec.add(StepRecord(step_index=1, action="click", action_description="点击登录"))
    html = render_html(rec, tmp_path).read_text(encoding="utf-8")
    assert "点击登录" in html


def test_render_html_escapes_script_close_in_data(tmp_path):
    # DOM 文本含 </script> 不能提前关闭内联 <script>（否则整页白屏）。
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    rec.add(StepRecord(step_index=1, action="click",
                       action_description="</script><h1>pwned",
                       dom_tree={"platform": "web",
                                 "nodes": [{"class": "x", "text": "</script>"}]}))
    html = render_html(rec, tmp_path).read_text(encoding="utf-8")
    # 原始 </script> 不得出现在数据里；只应是被转义的 <\/script>
    assert "</script><h1>pwned" not in html
    assert "<\\/script>" in html
