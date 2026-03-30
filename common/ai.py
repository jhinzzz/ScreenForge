import json
import time
from openai import OpenAI

import config.config as config
from common.logs import log
from common.cache import CacheManager


class AIBrain:
    def __init__(self):
        # 实例化文本专属客户端
        self.text_client = OpenAI(
            api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL
        )

        # 实例化视觉专属客户端
        self.vision_client = OpenAI(
            api_key=config.VISION_API_KEY, base_url=config.VISION_BASE_URL
        )

        self.cache_manager = CacheManager(
            cache_dir=config.CACHE_DIR,
            enabled=config.CACHE_ENABLED,
            ttl_days=config.CACHE_TTL_DAYS,
            max_size_mb=config.CACHE_MAX_SIZE_MB,
        )

    def _verify_locator_in_ui(self, decision: dict, ui_dict: dict) -> bool:
        """
        校验缓存中推荐的动作，其元素是否真实存在于当前的 UI 树中
        """
        loc_type = decision.get("locator_type")
        loc_val = decision.get("locator_value")

        # 如果动作不需要特定元素 (比如 answer 或某些全局操作)，直接放行
        if (
            not loc_type
            or not loc_val
            or loc_type not in ["text", "description", "resourceId"]
        ):
            return True

        elements = ui_dict.get("ui_elements", [])
        for el in elements:
            if loc_type == "text" and el.get("text") == loc_val:
                return True
            if loc_type == "description" and el.get("desc") == loc_val:
                return True
            if loc_type == "resourceId" and el.get("id") == loc_val:
                return True

        return False

    def get_action(
        self,
        instruction: str,
        ui_json: str,
        screenshot_base64: str = None,
        chat_history: list = None,
    ) -> dict:
        """
        向大模型发送指令并返回结构化动作 JSON。
        """
        try:
            ui_dict = json.loads(ui_json)
        except json.JSONDecodeError:
            ui_dict = {}

        # ==========================================
        # 1. 缓存读取与物理校验阶段
        # ==========================================
        cached_l1 = self.cache_manager.get(instruction, ui_dict)
        if cached_l1 is not None:
            log.info("🎯 [Cache] 命中页面级精准缓存 (L1-Action)")
            return cached_l1

        if hasattr(self.cache_manager, "get_chat_simple"):
            cached_l2 = self.cache_manager.get_chat_simple(instruction)
            if cached_l2 is not None:
                # 在当前页面观察元素是否存在，若不存在则放弃缓存
                if self._verify_locator_in_ui(cached_l2, ui_dict):
                    log.info("🎯 [Cache] 命中全局语义缓存 (L2-Semantic)")
                    return cached_l2
                else:
                    log.warning(
                        "⚠️ [Cache] 语义缓存虽命中，但目标元素在当前页面不存在，已放弃该缓存..."
                    )

        log.info("❌ [Cache Miss] 缓存未命中，准备请求大模型 API...")
        # ==========================================
        # 2. 处理上下文历史 (触发大模型 Prompt Caching)
        # ==========================================
        history_prompt = ""
        if chat_history:
            # 仅提取历史意图和动作，丢弃庞大的历史 UI 树以防止 Context 爆炸
            history_str = "\n".join(
                [
                    f"- 历史步骤{i + 1}: {step.get('action_description')}"
                    for i, step in enumerate(chat_history)
                ]
            )
            history_prompt = (f"\n\n【前置对话上下文】(请结合上下文理解当前指令):\n{history_str}")

        # ==========================================
        # 3. 提示词与 Payload 组装
        # ==========================================
        vision_prompt = ""
        if screenshot_base64:
            vision_prompt = """
                你同时收到了一张真实屏幕截图。请优先结合视觉画面判断页面结构和元素状态！如果 XML 树找不到或者混乱，以视觉为准。
            """
        system_prompt = f"""
        # Role: 自动化测试策略生成专家

        ## Profile
        - language: 中文
        - description: 资深自动化测试专家，专门分析UI元素树和视觉画面，将自然语言测试指令转化为可执行的自动化操作策略
        - background: 拥有10年以上UI自动化测试经验，精通各种测试框架和元素定位技术，擅长处理动态UI和复杂交互场景
        - personality: 严谨、细致、逻辑性强，注重测试的准确性和可重复性
        - expertise: UI元素分析、测试策略制定、定位器选择优化、跨平台测试适配
        - target_audience: 测试工程师、开发人员、质量保证团队

        ## Skills

        1. 元素分析技能
        - UI结构解析: 能够深度解析XML/JSON格式的UI元素树，理解页面层级结构
        - 视觉辅助判断: 结合屏幕截图验证元素状态和布局，解决元素树不准确的问题
        - 动态元素识别: 识别并处理动态生成的CSS、resourceId等不稳定定位器
        - 元素属性评估: 分析元素的text、description、resourceId等关键属性

        2. 测试策略制定技能
        - 指令解析: 准确理解用户的自然语言测试指令，转化为具体操作步骤
        - 定位器选择: 根据优先级规则选择最稳定可靠的元素定位方式
        - 操作映射: 将测试需求映射到具体的自动化操作类型
        - 异常处理: 预判可能出现的测试异常并提供应对策略

        ## Rules (核心原则)

        1. 基本原则：
        - 视觉优先原则: 当XML元素树与视觉画面不一致时，以视觉画面为准进行判断
        - 稳定性优先: 选择定位器时，稳定性比简洁性更重要，避免使用动态生成的定位器
        - 准确性保证: 确保生成的测试策略能够准确执行用户的测试意图
        - 完整性要求: 输出必须包含所有必要的操作参数，确保测试可执行

        2. 行为准则：
        - 严格遵循定位器优先级: css > resourceId > text > description
        - 动态检测机制: 自动检测并规避动态生成的css和resourceId
        - 上下文感知: 结合页面整体结构理解元素关系和状态
        - 验证机制: 对选择的定位器进行逻辑验证，确保唯一性和可访问性

        ## 📋 执行协议 (Protocol)
        {vision_prompt}

        ### 允许的 Action 类型
        - "click": 点击元素
        - "input": 在输入框中输入内容
        - "assert_exist": 校验某个元素是否在页面上出现
        - "assert_text_equals": 校验某个元素的文本是否与期望值一致

        ### 定位器选择铁律
        1. 优先级顺序：css > resourceId > text > description
        2. 【🚨 降级原则】当发现 css 或 resourceId 是动态生成的（包含随机hash、时间戳），请严格降级并优先选择 "text" 或 "description"！

        ### 强制输出格式
        必须输出纯 JSON 对象，不要包含任何 markdown 格式，包含顶级 key "result"，内部结构如下:
        {{"result": {{"action": "...", "locator_type": "...", "locator_value": "...", "extra_value": "..."}}}}

        ## Workflows

        - 目标: 将用户的测试指令转化为可执行的自动化测试策略
        - 步骤 1: 接收并分析UI元素树（JSON格式），同时检查是否有视觉辅助截图
        - 步骤 2: 解析用户的自然语言测试指令，明确测试意图和期望结果
        - 步骤 3: 结合元素树和视觉画面，确定目标元素及其状态
        - 步骤 4: 根据定位器优先级规则，选择最稳定可靠的定位器
        - 步骤 5: 将测试指令映射到具体的操作类型，并准备必要参数
        - 步骤 6: 按照指定格式输出JSON格式的测试策略
        - 预期结果: 生成一个完整、准确、可执行的自动化测试操作策略

        ## Initialization
        作为自动化测试策略生成专家，你必须遵守上述Rules，严格按照【执行协议】输出结果。
        """

        user_prompt = f"用户指令: {instruction}{history_prompt}\n当前屏幕 UI 树:\n{ui_json}"
        user_message_content = [{"type": "text", "text": user_prompt}]

        if screenshot_base64:
            user_message_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"},
                }
            )

        # ==========================================
        # 3. 动态智能路由
        # ==========================================
        if screenshot_base64:
            active_client = self.vision_client
            active_model = config.VISION_MODEL_NAME
            log.info(f"👁️ 调用多模态视觉模型: {active_model}")
        else:
            active_client = self.text_client
            active_model = config.MODEL_NAME

        start_time = time.time()
        decision = self._call_llm(active_client, active_model, system_prompt, user_message_content)
        llm_latency = time.time() - start_time
        log.info(f"⏱️ [AI] AI 思考完毕，网络请求耗时: {llm_latency:.2f} 秒")

        # ==========================================
        # 4. 缓存全量回写阶段
        # ==========================================
        if decision:
            # 1. 只要成功，必然写入强绑定的页面缓存 (L1)
            self.cache_manager.set(instruction, ui_dict, decision, llm_latency=llm_latency)

            # 2. 放开 L2 写入
            if hasattr(self.cache_manager, "set_chat_simple"):
                self.cache_manager.set_chat_simple(instruction, decision, llm_latency=llm_latency)

        return decision

    def _call_llm(
        self,
        client: OpenAI,
        model_name: str,
        system_prompt: str,
        user_message_content: list,
    ) -> dict:
        """
        封装底层的 LLM 网络调用
        """
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message_content},
                ],
                temperature=0.1,
            )

            result_text = response.choices[0].message.content.strip()

            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.replace("```", "").strip()

            parsed_json = json.loads(result_text)
            return parsed_json.get("result", {})

        except Exception as e:
            log.error(f"[Error] 模型({model_name})请求或解析失败: {e}")
            return {}
