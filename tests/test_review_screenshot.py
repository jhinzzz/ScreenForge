"""截图持久化 + 缩略图。用 Pillow 造一张真 PNG（Pillow 已装，见 conftest.py:94）。"""

import base64
import io

from PIL import Image

from review.render import make_thumbnail, save_screenshot


def _png_bytes(w=1280, h=720, color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


class _FakePage:
    def screenshot(self): return _png_bytes()


def test_make_thumbnail_is_jpeg_datauri_and_smaller():
    big = _png_bytes(1280, 720)
    uri = make_thumbnail(big, max_w=400)
    assert uri.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(uri.split(",", 1)[1])
    # 缩略图（400px JPEG）应远小于原 1280px PNG
    assert len(decoded) < len(big)
    img = Image.open(io.BytesIO(decoded))
    assert img.width == 400


def test_save_screenshot_writes_png_and_returns_relpath(tmp_path):
    rel, thumb = save_screenshot(_FakePage(), tmp_path, 1)
    assert rel == "screenshots/step_001.png"
    assert (tmp_path / "screenshots" / "step_001.png").is_file()
    assert thumb.startswith("data:image/jpeg;base64,")


def test_save_screenshot_pads_index(tmp_path):
    rel, _ = save_screenshot(_FakePage(), tmp_path, 42)
    assert rel == "screenshots/step_042.png"
