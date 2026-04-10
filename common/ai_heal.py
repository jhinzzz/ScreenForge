"""AI Self-Healing Engine — structured JSON output with confidence scoring."""

import ast
import json
import re
import time
from dataclasses import dataclass

from common.logs import log


@dataclass
class HealResult:
    """Self-heal attempt result."""

    confidence: float  # 0.0 - 1.0
    fix_description: str
    fixed_code: str

    @property
    def is_valid_syntax(self) -> bool:
        try:
            ast.parse(self.fixed_code)
            return True
        except SyntaxError:
            return False


def _parse_heal_response(raw: str) -> HealResult:
    """Parse LLM response into HealResult. Tries multiple extraction strategies."""

    # Strategy 1: direct JSON parse
    try:
        data = json.loads(raw)
        return HealResult(
            confidence=float(data.get("confidence", 0.0)),
            fix_description=str(data.get("fix_description", "")),
            fixed_code=str(data.get("fixed_code", "")),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Strategy 2: extract JSON from markdown code fence or surrounding text
    # First try ```json ... ``` blocks
    json_fence = re.search(r"```(?:json)?\s*\n(\{[\s\S]*?\})\s*\n```", raw)
    if json_fence:
        try:
            data = json.loads(json_fence.group(1))
            if "fixed_code" in data:
                return HealResult(
                    confidence=float(data.get("confidence", 0.0)),
                    fix_description=str(data.get("fix_description", "")),
                    fixed_code=str(data.get("fixed_code", "")),
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Then try balanced-brace extraction from raw text
    for m in re.finditer(r"\{", raw):
        start = m.start()
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(raw)):
            c = raw[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start : i + 1]
                    try:
                        data = json.loads(candidate)
                        if "fixed_code" in data:
                            return HealResult(
                                confidence=float(data.get("confidence", 0.0)),
                                fix_description=str(data.get("fix_description", "")),
                                fixed_code=str(data.get("fixed_code", "")),
                            )
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                    break

    # Strategy 3: fallback — extract python code block (legacy format), low confidence
    code_match = re.search(r"```python\n(.*?)\n```", raw, re.DOTALL)
    if code_match:
        return HealResult(
            confidence=0.3,
            fix_description="(fallback: extracted from markdown code block)",
            fixed_code=code_match.group(1).strip(),
        )

    # Strategy 4: last resort — strip backticks
    stripped = raw.replace("```python", "").replace("```", "").strip()
    if "def test_" in stripped:
        return HealResult(
            confidence=0.2,
            fix_description="(fallback: raw text extraction)",
            fixed_code=stripped,
        )

    return HealResult(confidence=0.0, fix_description="failed to parse response", fixed_code="")


class HealerBrain:
    """AI Self-Healing Engine."""

    def __init__(self):
        from openai import OpenAI

        import config.config as config

        self.client = OpenAI(
            api_key=config.VISION_API_KEY, base_url=config.VISION_BASE_URL
        )
        self.model_name = config.VISION_MODEL_NAME

    def heal_script(
        self,
        script_content: str,
        error_msg: str,
        error_line_num: int,
        ui_json: str,
        screenshot_base64: str,
        platform: str,
    ) -> HealResult:
        """Analyze failure and generate fix. Returns HealResult (never None)."""
        log.info(
            f"🧠 [HealerBrain] Analyzing {platform} failure at line {error_line_num}..."
        )
        start_time = time.time()

        system_prompt = """你是一个自动化测试自愈引擎。当测试用例执行失败时，你负责分析原因并生成修复代码。

【输入】
1. 报错行号和异常堆栈
2. 案发瞬间的 UI 元素树 (JSON) 和截图
3. 原始测试脚本

【思考步骤】
1. 分析报错：元素找不到？Strict Mode 多元素冲突？弹窗遮挡？
2. 观察 UI 树和截图，找到目标元素当前的实际状态
3. 在保证业务流完整性的前提下，修改失败的定位器代码

【输出格式 — 必须返回 JSON】
{
  "confidence": 0.0到1.0的浮点数,
  "fix_description": "简短描述修复了什么",
  "fixed_code": "完整的修复后 Python 脚本代码"
}

confidence 含义：
- 0.9-1.0: 明确找到了元素变化，修复方案确定
- 0.7-0.8: 找到了可能的匹配，修复方案较有把握
- 0.5-0.6: 不太确定，但做了最佳猜测
- <0.5: 不确定修复是否正确

注意：fixed_code 中的换行用 \\n 表示，确保 JSON 可解析。只返回 JSON，不要其他文字。"""

        user_prompt = f"""【报错平台】: {platform}
【报错行号】: 第 {error_line_num} 行
【异常信息】: {error_msg}

【UI 树】:
{ui_json}

【原始脚本】:
{script_content}

请返回 JSON 格式的修复方案。"""

        messages = [{"role": "system", "content": system_prompt}]
        user_content = [{"type": "text", "text": user_prompt}]
        if screenshot_base64:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"},
                }
            )
        messages.append({"role": "user", "content": user_content})

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.1,
            )

            raw = response.choices[0].message.content.strip()
            result = _parse_heal_response(raw)

            # Syntax validation — invalid syntax forces confidence to 0
            if result.fixed_code and not result.is_valid_syntax:
                log.warning("⚠️ [HealerBrain] Generated code has syntax errors, rejecting")
                result = HealResult(
                    confidence=0.0,
                    fix_description=f"syntax error in generated code: {result.fix_description}",
                    fixed_code="",
                )

            latency = time.time() - start_time
            log.info(
                f"⏱️ [HealerBrain] Done in {latency:.2f}s "
                f"(confidence={result.confidence:.2f}, desc={result.fix_description[:80]})"
            )
            return result

        except Exception as e:
            log.error(f"❌ [HealerBrain] API call failed: {e}")
            return HealResult(confidence=0.0, fix_description=f"API error: {e}", fixed_code="")
