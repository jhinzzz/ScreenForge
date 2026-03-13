import json
from openai import OpenAI

from logs import log
import config.config as config


class AIBrain:
    def __init__(self):
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL
        )

    def get_action(self, instruction: str, ui_json: str) -> dict:
        """向大模型发送指令并返回结构化动作 JSON"""

        system_prompt = """
        你是一个资深的 Android 自动化测试专家。
        根据提供的当前屏幕 UI 元素树 (JSON 格式)，理解用户的测试指令，并输出执行策略。

        允许的 action 类型:
        - "click": 点击元素
        - "input": 在输入框中输入内容
        - "assert_exist": 校验某个元素是否在页面上出现
        - "assert_text_equals": 校验某个元素的文本是否与期望值一致

        允许的 locator_type 类型 (优先级：id > text > description):
        - "resourceId" (对应 UI 树中的 id)
        - "text"
        - "description" (对应 UI 树中的 desc)

        【强制输出格式】
        必须输出纯 JSON 对象，不能包含任何其他文字或 markdown 格式，包含顶级 key "result"，内部结构如下:
        {"result": {"action": "...", "locator_type": "...", "locator_value": "...", "extra_value": "..."}}
        注: extra_value 用于 input 的输入文本，或 assert_text_equals 的期望文本。
        """

        user_prompt = f"用户指令: {instruction}\n当前屏幕 UI 树:\n{ui_json}"

        try:
            response = self.client.chat.completions.create(
                model=config.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )

            result_text = response.choices[0].message.content.strip()
            parsed_json = json.loads(result_text)
            return parsed_json.get("result", {})

        except Exception as e:
            log.error(f"\n[AI Error] 模型请求或解析失败: {e}")
            return {}
