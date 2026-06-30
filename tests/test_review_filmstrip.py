"""ffmpeg 胶片：mock subprocess，验证命令拼接与降级，不真跑 ffmpeg。"""

import review.render as render


def test_filmstrip_none_when_no_screenshots(tmp_path):
    assert render.make_filmstrip(tmp_path) is None


def test_filmstrip_invokes_ffmpeg_and_returns_relname(tmp_path, monkeypatch):
    shots = tmp_path / "screenshots"
    shots.mkdir()
    (shots / "step_001.png").write_bytes(b"x")
    calls = {}
    def fake_run(cmd, *a, **k):
        calls["cmd"] = cmd
        (tmp_path / "video.gif").write_bytes(b"GIF")   # 模拟 ffmpeg 产物
        class R: returncode = 0
        return R()
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    monkeypatch.setattr(render.shutil, "which", lambda name: "/opt/homebrew/bin/ffmpeg")
    rel = render.make_filmstrip(tmp_path)
    assert rel == "video.gif"
    assert "ffmpeg" in calls["cmd"][0]
    assert (tmp_path / "video.gif").is_file()


def test_filmstrip_none_when_ffmpeg_missing(tmp_path, monkeypatch):
    shots = tmp_path / "screenshots"
    shots.mkdir()
    (shots / "step_001.png").write_bytes(b"x")
    monkeypatch.setattr(render.shutil, "which", lambda name: None)
    assert render.make_filmstrip(tmp_path) is None
