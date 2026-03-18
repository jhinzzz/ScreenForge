import json
from openai import OpenAI

from common.logs import log
import config.config as config
from common.cache import CacheManager


class AIBrain:
    def __init__(self):
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL
        )
        self.cache_manager = CacheManager(
            cache_dir=config.CACHE_DIR,
            enabled=config.CACHE_ENABLED,
            ttl_days=config.CACHE_TTL_DAYS,
            max_size_mb=config.CACHE_MAX_SIZE_MB
        )

    def get_action(self, instruction: str, ui_json: str, raw_xml: str) -> dict:
        """向大模型发送指令并返回结构化动作 JSON"""
        try:
            ui_dict = json.loads(ui_json)
        except json.JSONDecodeError:
            ui_dict = {}

        # L1: 动作骨架缓存 (点击/输入)
        cached_l1 = self.cache_manager.get(instruction, ui_dict)
        if cached_l1:
            log.info(f"🎯 [Cache L1 Hit] 命中动作骨架缓存: {cached_l1.get('action')}")
            return cached_l1

        # L2: 问答数据缓存 (断言/数据提取)
        cached_l2 = self.cache_manager.get_chat(instruction, raw_xml)
        if cached_l2:
            log.info(f"🎯 [Cache L2 Hit] 命中 AI 问答缓存: {cached_l2.get('action')}")
            return cached_l2

        log.info("[Cache Miss] 调用 AI API")
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
            # 兼容大模型返回 markdown
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.replace("```", "").strip()

            try:
                parsed_json = json.loads(result_text)
                decision = parsed_json.get("result", {})
            except json.JSONDecodeError as e:
                log.error(f"[AI Error] 无法解析大模型返回的 JSON: {result_text}")
                return {}

            if decision:
                action_type = decision.get("action")
                # 智能路由回写
                if action_type in ["assert_exist", "assert_text_equals", "answer"]:
                    # 强依赖当前屏幕数据的，存入短效 L2 (5分钟)
                    self.cache_manager.set_chat(instruction, raw_xml, decision, ttl_seconds=300)
                else:
                    # 不依赖数据的纯动作，存入长效 L1
                    self.cache_manager.set(instruction, ui_dict, decision)

            return decision

        except Exception as e:
            log.error(f"[Error] 模型请求或网络通讯失败: {e}")
            return {}
