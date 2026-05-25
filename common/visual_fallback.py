"""Visual fallback: locate elements via VLM screenshot when DOM lookup fails."""

import json
import re

from common.logs import log


def visual_locate(screenshot_bytes: bytes, description: str) -> tuple[int, int] | None:
    import base64

    import config.config as config

    try:
        from openai import OpenAI
    except ImportError:
        log.error("[Visual Fallback] openai package not installed")
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
        json_match = re.search(r"\{[^}]+\}", raw)
        if not json_match:
            log.warning(f"[Visual Fallback] VLM response not parseable: {raw[:200]}")
            return None

        coords = json.loads(json_match.group())
        x = int(coords.get("x", -1))
        y = int(coords.get("y", -1))

        if x < 0 or y < 0:
            log.warning("[Visual Fallback] VLM could not locate target element")
            return None

        log.info(f"[Visual Fallback] VLM located element at ({x}, {y})")
        return (x, y)

    except Exception as e:
        log.error(f"[Visual Fallback] VLM call failed: {e}")
        return None
