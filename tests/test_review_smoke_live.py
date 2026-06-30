"""opt-in：RUN_LIVE_WEB_SMOKE=1 跑真实单页流程，断言产出 review.json + report.html。

使用离线 data: URL（确定性，无网络依赖）。复用 test_web_smoke_live.py 的 env 门控
+ _chromium_available() 守卫，无 Chromium 自跳过，不破坏纯 core 环境。
"""

import json
import os
from pathlib import Path

import pytest

_RUN = os.getenv("RUN_LIVE_WEB_SMOKE", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live_web,
    pytest.mark.skipif(
        not _RUN,
        reason="opt-in live web smoke; set RUN_LIVE_WEB_SMOKE=1 to run (needs real Chromium).",
    ),
]

# 离线页面：一个输入框 + 按钮，无网络依赖。
_PAGE = (
    "data:text/html,"
    "<h1>Review Smoke</h1>"
    "<input id='name' type='text'>"
    "<button id='go'>Go</button>"
)


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        pw = sync_playwright().start()
        path = pw.chromium.executable_path
        pw.stop()
        return bool(path) and os.path.exists(path)
    except Exception:
        return False


def test_review_records_real_run(tmp_path, monkeypatch):
    if not _chromium_available():
        pytest.skip("Playwright/Chromium not installed")

    monkeypatch.setenv("REVIEW_RECORD", "1")
    monkeypatch.setenv("TEST_PLATFORM", "web")

    from common.adapters import WebPlaywrightAdapter
    from review.patching import install_capture, uninstall_capture
    from review.recorder import get_recorder, reset_recorder
    from review.render import render_html, write_review_json

    out_dir = tmp_path / "review_out"
    reset_recorder()
    get_recorder().start_run(
        run_id="smoke", platform="web", test_file="smoke", out_dir=str(out_dir)
    )
    adapter = WebPlaywrightAdapter()
    adapter.setup()
    install_capture("web")
    try:
        d = adapter.driver
        d.goto(_PAGE, wait_until="load")
        d.locator("#name").first.fill("hello")
    finally:
        uninstall_capture()
        adapter.teardown()

    rec = get_recorder()
    assert len(rec.records) >= 2, f"expected >=2 records, got {len(rec.records)}"
    assert all(r.success for r in rec.records), "some steps failed"

    write_review_json(rec, out_dir)
    html = render_html(rec, out_dir)

    data = json.loads((out_dir / "review.json").read_text(encoding="utf-8"))
    assert data["steps"][0]["action"] == "goto"
    assert data["steps"][1]["action"] == "fill"
    assert data["steps"][1]["code_loc"], "code_loc is empty (frame location failed)"
    assert "fill" in data["steps"][1]["code_line"], (
        f"expected 'fill' in code_line, got: {data['steps'][1]['code_line']!r}"
    )
    assert Path(html).is_file(), "report.html not created"
    assert (out_dir / "screenshots" / "step_001.png").is_file(), "step_001.png missing"
