import json
from common.ai import AIBrain
from common.logs import log
import config.config as config


class AutonomousBrain(AIBrain):
    def get_execution_plan(
        self,
        goal: str,
        context: str,
        ui_json: str,
        history: list,
        platform: str = "android",
        screenshot_base64: str = None,
    ) -> dict:
        try:
            json.loads(ui_json)
        except json.JSONDecodeError:
            ui_json = '{"ui_elements": []}'

        history_str = "无"
        if history:
            history_str = "\n".join(
                [
                    f"第{i + 1}步: {step['action_description']}"
                    for i, step in enumerate(history)
                ]
            )

        system_prompt = f"""
        你是一个{platform} 自动化测试规划专家。
        你需要根据用户目标、上下文、历史步骤和当前页面 UI 树，输出一个执行前计划。

        你必须输出纯 JSON 对象，不要包含 markdown，结构如下：
        {{
            "current_state_summary": "当前页面状态摘要",
            "planned_steps": ["步骤1", "步骤2", "步骤3"],
            "suggested_assertion": "最终建议断言",
            "risks": ["风险1", "风险2"]
        }}
        """

        user_prompt = f"""
        【宏观测试目标】: {goal}
        【参考上下文(PRD/用例)】: {context if context else '无'}
        【已执行的历史步骤】:
        {history_str}
        【当前屏幕 UI 树】:
        {ui_json}
        """

        user_message_content = [{"type": "text", "text": user_prompt}]
        if screenshot_base64:
            user_message_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"},
                }
            )

        if screenshot_base64:
            active_client = getattr(self, "vision_client", None) or getattr(
                self, "text_client", None
            )
            active_model = config.VISION_MODEL_NAME
        else:
            active_client = getattr(self, "text_client", None) or getattr(
                self, "client", None
            )
            active_model = config.MODEL_NAME

        if not active_client:
            log.error("❌ [Error] 未找到可用的模型客户端，无法生成执行计划")
            return {
                "current_state_summary": "模型客户端未初始化",
                "planned_steps": [],
                "suggested_assertion": "",
                "risks": ["模型客户端未初始化"],
            }

        result_text = ""
        try:
            response = active_client.chat.completions.create(
                model=active_model,
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
            parsed_json.setdefault("current_state_summary", "")
            parsed_json.setdefault("planned_steps", [])
            parsed_json.setdefault("suggested_assertion", "")
            parsed_json.setdefault("risks", [])
            return parsed_json
        except Exception as e:
            log.error(f"[Error] 计划模型请求或解析失败: {e}\n模型返回: {result_text}")
            return {
                "current_state_summary": "计划生成失败",
                "planned_steps": [],
                "suggested_assertion": "",
                "risks": ["计划生成失败"],
            }

    def get_next_autonomous_action(
        self,
        goal: str,
        context: str,
        ui_json: str,
        history: list,
        platform: str = "android",
        last_error: str = "",
        screenshot_base64: str = None,
    ) -> dict:
        """
        向大模型发送宏观目标、当前状态、前置报错及视觉截图，自主决策下一步动作
        """
        try:
            json.loads(ui_json)
        except json.JSONDecodeError:
            ui_json = '{"ui_elements": []}'

        history_str = "无"
        if history:
            history_str = "\n".join(
                [
                    f"第{i + 1}步: {step['action_description']}"
                    for i, step in enumerate(history)
                ]
            )

        error_prompt = ""
        if last_error:
            error_prompt = f"\n⚠️ 【特别注意 - 上一步执行失败】:\n{last_error}\n请在本次思考中分析失败原因，尝试换一种动作或定位器。\n"

        vision_prompt = ""
        if screenshot_base64:
            vision_prompt = "\n👁️ 【视觉辅助】: 你同时收到了一张真实屏幕截图。请结合视觉画面与 UI 树，更精准地理解页面布局、按钮状态。如果 XML 树混乱，请以视觉画面为准。"

        system_prompt = f"""
        你是一个完全自主的{platform} {'多模态视觉' if screenshot_base64 else '纯文本'} 高级自动化测试 Agent。
        你需要根据用户的【宏观测试目标】、【参考上下文】、【已执行的历史步骤】以及【当前屏幕 UI 树】{'和【屏幕截图】' if screenshot_base64 else ''}，自主决定下一步需要执行什么动作。
        {vision_prompt}

        允许的 action 类型:
        - "click": 点击元素
        - "long_click": 长按元素
        - "hover": 悬停元素 (针对 Web 端，触发下拉菜单等交互)
        - "input": 在输入框中输入内容 (需通过 extra_value 参数提供内容)
        - "swipe": 滑动屏幕寻找不在视口内的元素。必须在 extra_value 填入 "up", "down", "left" 或 "right"。此时 locator_type 填 "global"。
        - "press": 模拟键盘或物理系统按键。必须在 extra_value 填入按键名 (如 "Enter", "Back")。此时 locator_type 填 "global"。
        - "assert_exist": 校验某个元素是否在页面上出现
        - "assert_text_equals": 校验某个元素的文本是否与期望值一致

        定位器 (locator_type) 优先级: css > resourceId > text > description
        🚨 警告: 若 resourceId 是动态随机的，必须降级使用 text 或 description！

        【思考与状态决策】
        你需要先思考 (thought)，然后评估当前状态 (status)：
        - "running": 目标尚未完成，需要执行下一步动作。
        - "success": 目标已达到最终校验阶段。⚠️ 强烈要求：宣告成功时，你必须在 result 中提供一个断言动作 (`assert_exist` 或 `assert_text_equals`)，底层引擎会执行该断言并固化到测试脚本中。
        - "failed": 遇到了无法克服的阻塞性错误，无法继续。

        【强制输出格式】
        必须输出纯 JSON 对象，不要包含任何 markdown 代码块标记，结构严格如下:
        {{
            "thought": "我现在的思考过程，我看到了什么，我接下来要干什么",
            "status": "running" | "success" | "failed",
            "result": {{"action": "...", "locator_type": "...", "locator_value": "...", "extra_value": "..."}}
        }}
        """

        user_prompt = f"""
        【宏观测试目标】: {goal}
        【参考上下文(PRD/用例)】: {context if context else '无'}
        【已执行的历史步骤】:
        {history_str}
        {error_prompt}
        【当前屏幕 UI 树】:
        {ui_json}
        """

        user_message_content = [{"type": "text", "text": user_prompt}]
        if screenshot_base64:
            user_message_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"},
                }
            )

        if screenshot_base64:
            active_client = getattr(self, "vision_client", None) or getattr(
                self, "text_client", None
            )  # 兼容配置
            active_model = config.VISION_MODEL_NAME
        else:
            active_client = getattr(self, "text_client", None) or getattr(
                self, "client", None
            )
            active_model = config.MODEL_NAME

        if not active_client:
            log.error("❌ [Error] 未找到可用的模型客户端，无法继续自主决策")
            return {
                "status": "failed",
                "thought": "模型客户端未初始化",
                "result": {},
            }

        log.info(f"🤖 [Autonomous] 正在使用模型 [{active_model}] 深度思考策略...")

        result_text = ""
        try:
            response = active_client.chat.completions.create(
                model=active_model,
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

            thought = parsed_json.get("thought", "无")
            status = parsed_json.get("status", "failed")
            log.info(f"🧠 [Agent 思考]: {thought}")
            log.info(f"🚩 [Agent 状态判定]: {status}")

            return parsed_json

        except Exception as e:
            log.error(f"[Error] 自主模型请求或解析失败: {e}\n模型返回: {result_text}")
            return {
                "status": "failed",
                "thought": "模型返回格式异常或请求失败",
                "result": {},
            }
