"""Review 报告渲染：截图持久化/缩略图、review.json 写出、HTML 烘焙、ffmpeg 胶片。"""

import base64
import io
import json
from pathlib import Path

from loguru import logger as log
from PIL import Image


def make_thumbnail(png_bytes: bytes, max_w: int = 400) -> str:
    """全分辨 PNG bytes → 等比缩到 max_w 宽的 JPEG data-uri（base64 内嵌用）。"""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, max(1, round(img.height * ratio))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def save_screenshot(page, out_dir: Path, step_index: int) -> tuple:
    """抓全分辨 PNG 落盘 out_dir/screenshots/step_NNN.png，返回 (相对路径, 缩略图b64)。"""
    png = page.screenshot()
    shots = Path(out_dir) / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    name = f"step_{step_index:03d}.png"
    (shots / name).write_bytes(png)
    rel = f"screenshots/{name}"
    try:
        thumb = make_thumbnail(png)
    except Exception as e:
        log.debug(f"[review] thumbnail skip: {e}")
        thumb = ""
    return rel, thumb


def write_review_json(recorder, out_dir: Path) -> Path:
    """把 recorder 的数据写成 out_dir/review.json（数据产物，解锁后续方向）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "review.json"
    path.write_text(
        json.dumps(recorder.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
