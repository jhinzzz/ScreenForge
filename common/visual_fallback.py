"""视觉 Fallback: 当 DOM 定位失败时, 通过 VLM 截图定位元素坐标。"""

import json
import re

from common.logs import log


def visual_locate(screenshot_bytes: bytes, description: str) -> tuple[int, int] | None:
    """通过 VLM 在截图中定位元素, 返回 (x, y) 中心坐标。

    Args:
        screenshot_bytes: 当前页面截图 PNG 字节
        description: 元素描述 (如 "text=合约", "css=#login-btn")

    Returns:
        (x, y) 像素坐标, 或 None (定位失败)
    """
    import base64

    import config.config as config

    try:
        from openai import OpenAI
    except ImportError:
        log.error("❌ [Visual Fallback] 缺少 openai 库")
        return None

    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    prompt = (
        f"你是一个 UI 元素定位专家。用户在页面上找不到元素: {description}\n"
        "请在截图中找到最匹配的元素, 返回该元素中心点的像素坐标。\n"
        "只返回 JSON, 格式: {\"x\": 数字, \"y\": 数字}\n"
        "如果找不到, 返回: {\"x\": -1, \"y\": -1}"
    )

    try:
        client = OpenAI(
            api_key=config.VISION_API_KEY,
            base_url=config.VISION_BASE_URL,
        )
        response = client.chat.completions.create(
            model=config.VISION_MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                        },
                    ],
                }
            ],
            max_tokens=100,
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()
        # 提取 JSON (可能包裹在 markdown 代码块中)
        json_match = re.search(r"\{[^}]+\}", raw)
        if not json_match:
            log.warning(f"⚠️ [Visual Fallback] VLM 返回无法解析: {raw[:200]}")
            return None

        coords = json.loads(json_match.group())
        x = int(coords.get("x", -1))
        y = int(coords.get("y", -1))

        if x < 0 or y < 0:
            log.warning("⚠️ [Visual Fallback] VLM 未找到目标元素")
            return None

        log.info(f"👁️ [Visual Fallback] VLM 定位成功: ({x}, {y})")
        return (x, y)

    except Exception as e:
        log.error(f"❌ [Visual Fallback] VLM 调用失败: {e}")
        return None
