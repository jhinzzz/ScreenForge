from abc import ABC, abstractmethod
from common.logs import log
import config.config as config

# 模块级 UI 元素缓存, 由 inspect_ui 写入, ref 定位器读取
_cached_ui_elements: list[dict] = []


def set_ui_elements(elements: list[dict]) -> None:
    """缓存最近一次 inspect_ui 返回的元素列表 (含 ref/x/y/w/h)"""
    global _cached_ui_elements
    _cached_ui_elements = list(elements) if elements else []


def _resolve_ref(ref_value: str) -> dict | None:
    """根据 ref 值 (如 @5) 查找缓存中的元素"""
    for el in _cached_ui_elements:
        if el.get("ref") == ref_value:
            return el
    return None


def _escape_locator_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _escape_python_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


class LocatorBuilder:
    @staticmethod
    def build_code(platform: str, u2_key: str, l_value: str) -> str:
        safe_val = _escape_locator_value(l_value)
        if platform == "web":
            if u2_key == "ref":
                # ref 定位: 查找元素, 降级为具体 locator 写入脚本
                el_data = _resolve_ref(l_value)
                if el_data and el_data.get("id"):
                    return f"locator('#{_escape_locator_value(el_data['id'])}').first"
                if el_data and el_data.get("text"):
                    return f"get_by_text('{_escape_locator_value(el_data['text'])}').first"
                # 坐标兜底
                if el_data:
                    cx = el_data.get("x", 0) + el_data.get("w", 0) // 2
                    cy = el_data.get("y", 0) + el_data.get("h", 0) // 2
                    return f"mouse.click({cx}, {cy})  # ref {l_value} coordinate fallback"
                return f"locator('{safe_val}').first"
            elif u2_key in ["resourceId", "id"]:
                return f"locator('#{safe_val}').first"
            elif u2_key == "text":
                return f"get_by_text('{safe_val}').first"
            elif u2_key == "description":
                return f"locator('[aria-label=\"{safe_val}\"]').first"
            else:
                return f"locator('{safe_val}').first"
        else:
            return f"{u2_key}='{safe_val}'"

    @staticmethod
    def get_element(d, platform: str, u2_key: str, l_value: str):
        if platform == "web":
            if u2_key == "ref":
                # ref 定位: 优先用 id/text, 兜底用坐标点击
                el_data = _resolve_ref(l_value)
                if not el_data:
                    log.warning(f"⚠️ [Ref] 未找到 {l_value}, 缓存中共 {len(_cached_ui_elements)} 个元素")
                    return None
                if el_data.get("id"):
                    return d.locator(f"#{el_data['id']}").first
                if el_data.get("text"):
                    return d.get_by_text(el_data["text"]).first
                # 坐标兜底: 返回 None, 由 execute_and_record 处理坐标点击
                return None
            elif u2_key in ["resourceId", "id"]:
                return d.locator(f"#{l_value}").first
            elif u2_key == "text":
                return d.get_by_text(l_value).first
            elif u2_key == "description":
                return d.locator(f"[aria-label='{l_value}']").first
            else:
                return d.locator(l_value).first
        else:
            return d(**{u2_key: l_value})


def build_locator_code(platform: str, u2_key: str, l_value: str) -> str:
    return LocatorBuilder.build_code(platform, u2_key, l_value)


def get_actual_element(d, platform: str, u2_key: str, l_value: str):
    return LocatorBuilder.get_element(d, platform, u2_key, l_value)


class ActionHandler(ABC):
    @abstractmethod
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        pass

    @abstractmethod
    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        pass

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        pass


class HoverHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform == "web":
            element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
            element.hover()
            return True
        else:
            log.warning("⚠️ [Warning] 移动端不支持 hover，跳过物理悬停操作")
            return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('悬停元素: [{l_value}]'):\n",
                f"        log.info('✅ [Action] 悬停元素 [{l_value}]')\n",
                f"        d.{loc_str}.hover(timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('悬停元素 (移动端忽略): [{l_value}]'):\n",
                f"        log.warning('⚠️ [Warning] 移动端不支持悬停 [{l_value}]')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"✅ [Action] 正在等待并悬停: {l_type}='{l_value}'"


class ClickHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform == "web":
            element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
            element.click()
            return True
        else:
            if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                return False
            element.click()
            return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('点击元素: [{l_value}]'):\n",
                f"        log.info('执行操作: 点击元素 [{l_value}]')\n",
                f"        d.{loc_str}.click(timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('点击元素: [{l_value}]'):\n",
                f"        log.info('执行操作: 点击元素 [{l_value}]')\n",
                f"        d({loc_str}).wait(timeout={timeout})\n",
                f"        d({loc_str}).click()\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"✅ [Action] 正在等待并点击: {l_type}='{l_value}'"


class LongClickHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if not element:
            return False
        if platform == "web":
            element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
            element.click(delay=1000)
            return True
        else:
            if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                return False
            element.long_click()
            return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('长按元素: [{l_value}]'):\n",
                f"        log.info('执行操作: 长按元素 [{l_value}]')\n",
                f"        d.{loc_str}.click(delay=1000, timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('长按元素: [{l_value}]'):\n",
                f"        log.info('执行操作: 长按元素 [{l_value}]')\n",
                f"        d({loc_str}).wait(timeout={timeout})\n",
                f"        d({loc_str}).long_click()\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"✅ [Action] 正在等待并长按: {l_type}='{l_value}'"


class InputHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform == "web":
            element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
            element.fill(extra_value)
            return True
        else:
            if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                return False
            element.set_text(extra_value)
            return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        safe_extra = _escape_python_string(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('输入文本: [{safe_extra}] 到 [{l_value}]'):\n",
                f"        log.info('执行操作: 在 [{l_value}] 输入 [{safe_extra}]')\n",
                f"        d.{loc_str}.fill('{safe_extra}', timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('输入文本: [{safe_extra}] 到 [{l_value}]'):\n",
                f"        log.info('执行操作: 在 [{l_value}] 输入 [{safe_extra}]')\n",
                f"        d({loc_str}).wait(timeout={timeout})\n",
                f"        d({loc_str}).set_text('{safe_extra}')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] 正在等待并输入: {l_type}='{l_value}', 内容='{extra_value}'"


class SwipeHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        direction = extra_value.lower() if extra_value else "down"
        if platform == "web":
            if direction == "up":
                d.mouse.wheel(0, -600)
            elif direction == "left":
                d.mouse.wheel(-600, 0)
            elif direction == "right":
                d.mouse.wheel(600, 0)
            else:
                d.mouse.wheel(0, 600)
            d.wait_for_timeout(1000)
        else:
            d.swipe_ext(direction)
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        direction = extra_value.lower() if extra_value else "down"
        if platform == "web":
            scroll_code = "d.mouse.wheel(0, 600)"
            if direction == "up":
                scroll_code = "d.mouse.wheel(0, -600)"
            elif direction == "left":
                scroll_code = "d.mouse.wheel(-600, 0)"
            elif direction == "right":
                scroll_code = "d.mouse.wheel(600, 0)"

            return [
                f"    with allure.step('滑动屏幕: [{direction}]'):\n",
                f"        log.info('执行操作: 滑动屏幕 [{direction}]')\n",
                f"        {scroll_code}\n",
                f"        d.wait_for_timeout(1000)\n",
            ]
        else:
            return [
                f"    with allure.step('滑动屏幕: [{direction}]'):\n",
                f"        log.info('执行操作: 向上/下/左/右 滑动屏幕 [{direction}]')\n",
                f"        d.swipe_ext('{direction}')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] 全局动作：正在滑动屏幕，方向='{extra_value}'"


class PressHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        key = extra_value if extra_value else "Enter"
        if platform == "web":
            d.keyboard.press(key)
            d.wait_for_timeout(500)
        else:
            d.press(key.lower())
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        key = extra_value if extra_value else "Enter"
        safe_key = _escape_python_string(key)
        if platform == "web":
            return [
                f"    with allure.step('触发按键: [{safe_key}]'):\n",
                f"        log.info('执行操作: 模拟键盘按键 [{safe_key}]')\n",
                f"        d.keyboard.press('{safe_key}')\n",
                f"        d.wait_for_timeout(500)\n",
            ]
        else:
            return [
                f"    with allure.step('触发物理按键: [{safe_key}]'):\n",
                f"        log.info('执行操作: 模拟手机系统按键 [{safe_key}]')\n",
                f"        d.press('{safe_key.lower()}')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] 全局动作：正在触发按键事件，按键='{extra_value}'"


class AssertExistHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        try:
            if platform == "web":
                element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
                is_exist = element.is_visible()
            else:
                is_exist = element.wait(timeout=config.DEFAULT_TIMEOUT)

                if not is_exist:
                    log.warning("❌ [Warning] 元素未出现 (但仍会生成断言代码)")
                else:
                    log.info("[Assert] 校验通过")
        except Exception:
            log.warning("❌ [Warning] 等待元素超时 (但仍会生成断言代码)")
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('断言: 验证元素 [{l_value}] 存在'):\n",
                f"        log.info('执行断言: 检查元素 [{l_value}] 是否存在')\n",
                f"        import playwright.sync_api\n",
                f"        try:\n",
                f"            d.{loc_str}.wait_for(state='visible', timeout={timeout * 1000})\n",
                f"            is_exist = True\n",
                f"        except playwright.sync_api.TimeoutError:\n",
                f"            is_exist = False\n",
                f"        if not is_exist:\n",
                f"            log.error('断言失败: 期望元素 [{l_value}] 未出现')\n",
                f"        assert is_exist, '断言失败: 期望元素 {l_value} 未出现'\n",
                f"        log.info('断言成功: 元素已出现')\n",
            ]
        else:
            return [
                f"    with allure.step('断言: 验证元素 [{l_value}] 存在'):\n",
                f"        log.info('执行断言: 检查元素 [{l_value}] 是否存在')\n",
                f"        is_exist = d({loc_str}).wait(timeout={timeout})\n",
                f"        if not is_exist:\n",
                f"            log.error('断言失败: 期望元素 [{l_value}] 未出现')\n",
                f"        assert is_exist, '断言失败: 期望元素 {l_value} 未出现'\n",
                f"        log.info('断言成功: 元素已出现')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] 校验元素存在: {l_type}='{l_value}'"


class AssertTextEqualsHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        try:
            if platform == "web":
                element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
                actual_text = element.inner_text().strip()
            else:
                if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                    return False
                actual_text = element.get_text()

            if actual_text != extra_value:
                log.warning(f"[Warning] 期望 '{extra_value}', 实际 '{actual_text}'")
            else:
                log.info("[Assert] 校验通过")
        except Exception:
            log.warning("[Warning] 获取文本失败 (但仍会生成断言代码)")
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        safe_expected = _escape_python_string(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('断言: 验证元素文本等于 [{safe_expected}]'):\n",
                f"        log.info('执行断言: 检查元素 [{l_value}] 文本是否为 [{safe_expected}]')\n",
                f"        actual_text = d.{loc_str}.inner_text().strip()\n",
                f"        if actual_text != '{safe_expected}':\n",
                f"            log.error(f'断言失败: 期望 [{safe_expected}], 实际 [{{actual_text}}]')\n",
                f"        assert actual_text == '{safe_expected}', f'断言失败: 期望 {safe_expected}, 实际 {{actual_text}}'\n",
                f"        log.info(f'断言成功: 元素文本确为 [{safe_expected}]')\n",
            ]
        else:
            return [
                f"    with allure.step('断言: 验证元素文本等于 [{safe_expected}]'):\n",
                f"        log.info('执行断言: 检查元素 [{l_value}] 文本是否为 [{safe_expected}]')\n",
                f"        actual_text = d({loc_str}).get_text()\n",
                f"        if actual_text != '{safe_expected}':\n",
                f"            log.error(f'断言失败: 期望 [{safe_expected}], 实际 [{{actual_text}}]')\n",
                f"        assert actual_text == '{safe_expected}', f'断言失败: 期望 {safe_expected}, 实际 {{actual_text}}'\n",
                f"        log.info(f'断言成功: 元素文本确为 [{safe_expected}]')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] 校验文本一致: {l_type}='{l_value}', 期望='{extra_value}'"


class GotoHandler(ActionHandler):
    """Web 端页面导航动作：跳转到指定 URL"""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform != "web":
            log.warning("⚠️ [Warning] goto 动作仅支持 Web 平台")
            return False
        url = extra_value.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        d.goto(url, wait_until="domcontentloaded", timeout=config.DEFAULT_TIMEOUT * 1000)
        d.wait_for_timeout(2000)
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        url = extra_value.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        safe_url = _escape_python_string(url)
        return [
            f"    with allure.step('导航到: [{safe_url}]'):\n",
            f"        log.info('执行操作: 导航到 [{safe_url}]')\n",
            f"        d.goto('{safe_url}', wait_until='domcontentloaded')\n",
            f"        d.wait_for_timeout(2000)\n",
        ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] 正在导航到: {extra_value}"


class UIExecutor:
    _handlers = {}

    def __init__(self, device, platform="android"):
        self.d = device
        self.platform = platform
        if not self._handlers:
            self._handlers = {
                "click": ClickHandler(),
                "long_click": LongClickHandler(),
                "hover": HoverHandler(),
                "input": InputHandler(),
                "swipe": SwipeHandler(),
                "press": PressHandler(),
                "goto": GotoHandler(),
                "assert_exist": AssertExistHandler(),
                "assert_text_equals": AssertTextEqualsHandler(),
            }

    @classmethod
    def register_handler(cls, action_type: str, handler: ActionHandler):
        cls._handlers[action_type] = handler

    def execute_and_record(self, action_data: dict, file_obj=None) -> dict:
        action = action_data.get("action")
        l_type = action_data.get("locator_type", "global")
        l_value = action_data.get("locator_value", "global")
        extra_value = action_data.get("extra_value", "")

        result = {
            "success": False,
            "code_lines": [],
            "action_description": "",
            "action_info": {
                "action_type": action,
                "locator_type": l_type,
                "locator_value": l_value,
                "extra_value": extra_value,
            },
        }

        if not action:
            log.warning("⚠️ [System] AI 返回的动作类型为空，跳过执行。")
            return result

        handler = self._handlers.get(action)
        if not handler:
            log.error(f"❌ [Error] 不支持的动作类型: {action}")
            return result

        element = None
        u2_key = ""
        needs_locator = (
            l_value
            and str(l_value).lower() != "global"
            and str(l_type).lower() != "global"
        )
        if needs_locator:
            if not str(l_type).strip():
                log.error("❌ [Error] 元素类动作缺少 locator_type，放弃录制！")
                return result

            u2_locator_map = {
                "resourceId": "resourceId",
                "text": "text",
                "description": "description",
                "id": "resourceId",
                "ref": "ref",
            }
            u2_key = u2_locator_map.get(l_type, l_type)

            # ref 定位器: 缓存为空时自动 inspect 填充
            if u2_key == "ref" and not _cached_ui_elements and self.platform == "web":
                try:
                    from utils.utils_web import compress_web_dom
                    import json as _json
                    ui_json = compress_web_dom(self.d)
                    tree = _json.loads(ui_json)
                    set_ui_elements(tree.get("ui_elements", []))
                    log.info(f"🔍 [Ref] 自动 inspect 填充缓存: {len(_cached_ui_elements)} 个元素")
                except Exception as e:
                    log.warning(f"⚠️ [Ref] 自动 inspect 失败: {e}")

            try:
                element = get_actual_element(self.d, self.platform, u2_key, l_value)
            except Exception as e:
                log.warning(f"⚠️ [Warning] 生成元素定位器失败: {e}")
                return result

            # ref 定位器坐标兜底: element 为 None 但有坐标数据
            if element is None and u2_key == "ref" and self.platform == "web":
                el_data = _resolve_ref(l_value)
                if el_data and el_data.get("w", 0) > 0:
                    cx = el_data["x"] + el_data["w"] // 2
                    cy = el_data["y"] + el_data["h"] // 2
                    log.info(f"🎯 [Ref] {l_value} 使用坐标定位: ({cx}, {cy})")
                    try:
                        self.d.mouse.click(cx, cy)
                        code_lines = [
                            f"    with allure.step('点击元素: [{l_value}] (坐标定位)'):\n",
                            f"        log.info('执行操作: 点击 [{l_value}] at ({cx}, {cy})')\n",
                            f"        d.mouse.click({cx}, {cy})  # ref {l_value} coordinate fallback\n",
                        ]
                        result["success"] = True
                        result["code_lines"] = code_lines
                        result["action_description"] = f"🎯 [Ref] 点击 {l_value} at ({cx}, {cy})"
                        return result
                    except Exception as e:
                        log.error(f"❌ [Error] 坐标点击失败: {e}")
                        return result

            # 视觉 Fallback: DOM 定位失败时, 用 VLM 截图定位坐标
            if element is None and self.platform == "web":
                try:
                    from common.visual_fallback import visual_locate
                    screenshot_bytes = self.d.screenshot()
                    coords = visual_locate(
                        screenshot_bytes,
                        f"{l_type}={l_value}",
                    )
                    if coords:
                        cx, cy = coords
                        log.info(f"👁️ [Visual Fallback] 使用 VLM 坐标定位: ({cx}, {cy})")
                        self.d.mouse.click(cx, cy)
                        code_lines = [
                            f"    with allure.step('点击元素: [{l_value}] (视觉定位)'):\n",
                            f"        log.info('执行操作: 点击 [{l_value}] at ({cx}, {cy})')\n",
                            f"        d.mouse.click({cx}, {cy})  # visual fallback\n",
                        ]
                        result["success"] = True
                        result["code_lines"] = code_lines
                        result["action_description"] = f"👁️ [Visual Fallback] 点击 {l_value} at ({cx}, {cy})"
                        return result
                except Exception as e:
                    log.warning(f"⚠️ [Visual Fallback] 尝试失败: {e}")

            if element is None:
                log.error("❌ [Error] 元素定位器为空，放弃录制！")
                return result

        timeout = config.DEFAULT_TIMEOUT

        try:
            log.info(handler.get_log_message(l_type, l_value, extra_value))

            if element or action in ("goto", "swipe", "press"):
                if not handler.execute(self.d, element, self.platform, extra_value):
                    log.error(
                        f"❌ [Error] 动作执行受阻或 {timeout} 秒内未找到依赖元素，放弃录制！"
                    )
                    return result

            safe_u2_key = u2_key if needs_locator else ""
            code_lines = handler.generate_code(
                self.platform, safe_u2_key, l_value, extra_value, timeout
            )

            result["success"] = True
            result["code_lines"] = code_lines
            result["action_description"] = handler.get_log_message(
                l_type, l_value, extra_value
            )

            if file_obj is not None:
                for line in code_lines:
                    file_obj.write(line)
                file_obj.flush()

            return result

        except Exception as e:
            log.error(f"❌ [Execute Error] 执行时发生异常: {e}")
            return result
