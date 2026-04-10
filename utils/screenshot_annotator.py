"""截图标注器: 在截图上绘制红色矩形 + ref 标签, 帮助 Agent 直观定位元素。"""

import io

from PIL import Image, ImageDraw, ImageFont


def annotate_screenshot(png_bytes: bytes, ui_elements: list[dict]) -> bytes:
    """在截图上为可点击元素绘制红色边框和 ref 标签。

    Args:
        png_bytes: 原始截图的 PNG 字节
        ui_elements: compress_web_dom 返回的元素列表, 每个元素需含 ref/x/y/w/h

    Returns:
        标注后的 PNG 字节
    """
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except Exception:
        font = ImageFont.load_default()

    for el in ui_elements:
        if not el.get("clickable"):
            continue
        ref = el.get("ref", "")
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("w", 0)
        h = el.get("h", 0)
        if w <= 0 or h <= 0:
            continue

        # 红色半透明矩形边框
        draw.rectangle(
            [x, y, x + w, y + h],
            outline=(255, 0, 0, 200),
            width=2,
        )

        # ref 标签背景 + 文字
        if ref:
            label = ref
            bbox = font.getbbox(label)
            tw = bbox[2] - bbox[0] + 6
            th = bbox[3] - bbox[1] + 4
            # 标签放在元素左上角上方, 避免遮挡内容
            lx = x
            ly = max(y - th - 2, 0)
            draw.rectangle([lx, ly, lx + tw, ly + th], fill=(255, 0, 0, 220))
            draw.text((lx + 3, ly + 1), label, fill=(255, 255, 255, 255), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()
