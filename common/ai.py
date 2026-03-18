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
            max_size_mb=config.CACHE_MAX_SIZE_MB,
        )

    def get_action(self, instruction: str, ui_json: str) -> dict:
        """向大模型发送指令并返回结构化动作 JSON"""
        try:
            ui_dict = json.loads(ui_json)
        except json.JSONDecodeError:
            ui_dict = {}

        # ==========================================
        # L1 语义页面动作缓存
        # 适用场景：在相同骨架的页面，发出了意思极为相近的指令（如点击）
        # ==========================================
        cached_l1 = self.cache_manager.get(instruction, ui_dict)
        if cached_l1 is not None:
            return cached_l1

        # ==========================================
        # 语义纯问答缓存
        # 适用场景：不管在什么页面，只要问过类似的问题（断言/生成代码），直接取答案
        # ==========================================
        if hasattr(self.cache_manager, "get_chat_simple"):
            cached_l2 = self.cache_manager.get_chat_simple(instruction)
            if cached_l2 is not None:
                return cached_l2

        log.info("🐌 [Semantic Cache Miss] 语义缓存未命中，请求大模型 API 中...")
        system_prompt = """
        你是一个资深的 Android 自动化测试专家。
        根据提供的当前屏幕 UI 元素树 (JSON 格式)，理解用户的测试指令，并输出执行策略。

        允许的 action 类型:
        - "click": 点击元素
        - "input": 在输入框中输入内容
        - "assert_exist": 校验某个元素是否在页面上出现
        - "assert_text_equals": 校验某个元素的文本是否与期望值一致

        允许的 locator_type 类型及优先级说明:
        - 优先级顺序：css > resourceId > text > description
        - "css"
        - "resourceId" (对应 UI 树中的 id)
        - "text"
        - "description" (对应 UI 树中的 desc)

        【🚨 定位器选择重要原则】
        当发现 css 或 resourceId 是动态生成的（例如包含随机乱码、时间戳、自增长串数字等），请严格降级并优先选择 "text" 作为 locator_type！

        【强制输出格式】
        必须输出纯 JSON 对象，不要包含任何 markdown 格式，包含顶级 key "result"，内部结构如下:
        {"result": {"action": "...", "locator_type": "...", "locator_value": "...", "extra_value": "..."}}
        注: 如果页面中有多个相同文本的元素，请在 JSON 的 result 中增加 "index" 字段指明是第几个(从0开始计算)。
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

            # 兼容大模型有时强行输出 markdown 代码块的抽风情况
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.replace("```", "").strip()

            parsed_json = json.loads(result_text)
            decision = parsed_json.get("result", {})

            if decision:
                action_type = decision.get("action")
                if action_type in ["assert_exist", "assert_text_equals", "answer"]:
                    if hasattr(self.cache_manager, "set_chat_simple"):
                        self.cache_manager.set_chat_simple(instruction, decision)
                        log.info("💾 [Cache L2 Saved] 决策已存入【语义纯问答缓存】")
                else:
                    self.cache_manager.set(instruction, ui_dict, decision)
                    log.info("💾 [Cache L1 Saved] 决策已存入【语义动作缓存】")

            return decision

        except Exception as e:
            log.error(f"[Error] 模型请求或解析失败: {e}")
            return {}
