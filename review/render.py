"""Review 报告渲染：截图持久化/缩略图、review.json 写出、HTML 烘焙、ffmpeg 胶片。"""

import base64
import io
import json
import shutil
import subprocess
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
        json.dumps(recorder.to_dict(include_thumbs=False), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


_TEMPLATE_PATH = Path(__file__).parent / "report_template.html"


def render_html(recorder, out_dir: Path) -> Path:
    """把 review 数据烘焙进自包含 HTML（替换模板里的 /*__REVIEW_DATA__*/ 占位）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    # script-tag 内联 JSON 的标准缓解：
    #   </  → 防 DOM 文本里的 </script> 提前关闭 <script> 块、整页白屏；
    #   U+2028/U+2029 → JS 行分隔符，ensure_ascii=False 下会原样落进 <script>，
    #     裸字符直接断掉 const REVIEW=... 解析（页面文本含这两个码点时）。
    data_json = (
        json.dumps(recorder.to_dict(), ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    token = "/*__REVIEW_DATA__*/ null"
    if token not in template:  # 占位符与模板漂移时早失败，别静默产出 REVIEW=null 的白屏报告
        raise ValueError(f"review template missing data placeholder: {token!r}")
    html = template.replace(token, data_json, 1)
    path = out / "report.html"
    path.write_text(html, encoding="utf-8")
    return path


def make_filmstrip(out_dir: Path, fps: float = 1.5) -> str | None:
    """把 screenshots/*.png 拼成 video.gif（web 胶片）。无图/无 ffmpeg → None。"""
    out = Path(out_dir)
    shots = sorted((out / "screenshots").glob("step_*.png"))
    if not shots:
        return None
    if not shutil.which("ffmpeg"):
        log.warning("[review] ffmpeg not found; skipping filmstrip")
        return None
    gif = out / "video.gif"
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-pattern_type", "glob", "-i", str(out / "screenshots" / "step_*.png"),
        "-vf", "scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        str(gif),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0 or not gif.exists():
            log.warning("[review] ffmpeg filmstrip failed")
            return None
    except Exception as e:
        log.warning(f"[review] ffmpeg error: {e}")
        return None
    return "video.gif"
