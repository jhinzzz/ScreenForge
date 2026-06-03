from abc import ABC, abstractmethod

import config.config as config
from common.logs import log

_cached_ui_elements: list[dict] = []


def set_ui_elements(elements: list[dict]) -> None:
    global _cached_ui_elements
    _cached_ui_elements = list(elements) if elements else []


def _resolve_ref(ref_value: str) -> dict | None:
    for el in _cached_ui_elements:
        if el.get("ref") == ref_value:
            return el
    return None


def _escape_locator_value(value: str) -> str:
    s = str(value)
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")
    s = s.replace("\0", "\\x00")
    return s


def _escape_python_string(value: str) -> str:
    return _escape_locator_value(value)


class LocatorBuilder:
    @staticmethod
    def build_code(platform: str, u2_key: str, l_value: str) -> str:
        safe_val = _escape_locator_value(l_value)
        if platform == "web":
            if u2_key == "ref":
                el_data = _resolve_ref(l_value)
                if el_data and el_data.get("id"):
                    return f"locator('#{_escape_locator_value(el_data['id'])}').first"
                if el_data and el_data.get("text"):
                    return f"get_by_text('{_escape_locator_value(el_data['text'])}').first"
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
                el_data = _resolve_ref(l_value)
                if not el_data:
                    log.warning(f"[E030] Ref {l_value} not found in cache ({len(_cached_ui_elements)} elements available). Fix: run inspect_ui first to refresh the element cache")
                    return None
                if el_data.get("id"):
                    return d.locator(f"#{el_data['id']}").first
                if el_data.get("text"):
                    return d.get_by_text(el_data["text"]).first
                return None
            elif u2_key in ["resourceId", "id"]:
                return d.locator(f"#{l_value}").first
            elif u2_key == "text":
                return d.get_by_text(l_value).first
            elif u2_key == "description":
                return d.locator(f"[aria-label='{l_value}']").first
            else:
                return d.locator(l_value).first
        elif platform == "ios":
            ios_key_map = {
                "description": "label",
                "resourceId": "name",
                "text": "label",
                "css": "classChain",
            }
            mapped_key = ios_key_map.get(u2_key, u2_key)
            return d(**{mapped_key: l_value})
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
            log.warning("⚠️ [Warning] Hover not supported on mobile, skipping")
            return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('Hover: [{l_value}]'):\n",
                f"        log.info('Action: hover [{l_value}]')\n",
                f"        d.{loc_str}.hover(timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('Hover (mobile skip): [{l_value}]'):\n",
                f"        log.warning('Hover not supported on mobile [{l_value}]')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"✅ [Action] Hover: {l_type}='{l_value}'"


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
                f"    with allure.step('Click: [{l_value}]'):\n",
                f"        log.info('Action: click [{l_value}]')\n",
                f"        d.{loc_str}.click(timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('Click: [{l_value}]'):\n",
                f"        log.info('Action: click [{l_value}]')\n",
                f"        d({loc_str}).wait(timeout={timeout})\n",
                f"        d({loc_str}).click()\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"✅ [Action] Click: {l_type}='{l_value}'"


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
                f"    with allure.step('Long click: [{l_value}]'):\n",
                f"        log.info('Action: long click [{l_value}]')\n",
                f"        d.{loc_str}.click(delay=1000, timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('Long click: [{l_value}]'):\n",
                f"        log.info('Action: long click [{l_value}]')\n",
                f"        d({loc_str}).wait(timeout={timeout})\n",
                f"        d({loc_str}).long_click()\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"✅ [Action] Long click: {l_type}='{l_value}'"


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
                f"    with allure.step('Input: [{safe_extra}] into [{l_value}]'):\n",
                f"        log.info('Action: input [{safe_extra}] into [{l_value}]')\n",
                f"        d.{loc_str}.fill('{safe_extra}', timeout={timeout * 1000})\n",
            ]
        else:
            return [
                f"    with allure.step('Input: [{safe_extra}] into [{l_value}]'):\n",
                f"        log.info('Action: input [{safe_extra}] into [{l_value}]')\n",
                f"        d({loc_str}).wait(timeout={timeout})\n",
                f"        d({loc_str}).set_text('{safe_extra}')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] Input: {l_type}='{l_value}', value='{extra_value}'"


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
                f"    with allure.step('Swipe: [{direction}]'):\n",
                f"        log.info('Action: swipe [{direction}]')\n",
                f"        {scroll_code}\n",
                "        d.wait_for_timeout(1000)\n",
            ]
        else:
            return [
                f"    with allure.step('Swipe: [{direction}]'):\n",
                f"        log.info('Action: swipe [{direction}]')\n",
                f"        d.swipe_ext('{direction}')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] Swipe: direction='{extra_value}'"


class PressHandler(ActionHandler):
    _IOS_KEY_MAP = {
        "enter": ["前往", "Go", "go", "Search", "搜索", "return", "Return"],
        "return": ["前往", "Go", "go", "Search", "搜索", "return", "Return"],
        "search": ["搜索", "Search", "前往", "Go"],
        "done": ["完成", "Done"],
        "next": ["下一个", "Next"],
        "send": ["发送", "Send"],
    }

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        key = extra_value if extra_value else "Enter"
        if platform == "web":
            d.keyboard.press(key)
            d.wait_for_timeout(500)
        elif platform == "ios":
            key_lower = key.lower()
            if key_lower in ("home", "volumeup", "volumedown"):
                d.press(key_lower)
            else:
                candidates = self._IOS_KEY_MAP.get(key_lower, [key])
                for label in candidates:
                    try:
                        btn = d(label=label)
                        if btn.exists:
                            btn.click()
                            return True
                    except Exception:
                        continue
                d.press_key(0x28)
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
                f"    with allure.step('Press key: [{safe_key}]'):\n",
                f"        log.info('Action: press key [{safe_key}]')\n",
                f"        d.keyboard.press('{safe_key}')\n",
                "        d.wait_for_timeout(500)\n",
            ]
        elif platform == "ios":
            key_lower = key.lower()
            if key_lower in ("home", "volumeup", "volumedown"):
                return [
                    f"    with allure.step('Press key: [{safe_key}]'):\n",
                    f"        log.info('Action: press key [{safe_key}]')\n",
                    f"        d.press('{safe_key.lower()}')\n",
                ]
            candidates = self._IOS_KEY_MAP.get(key_lower, [key])
            first_label = _escape_python_string(candidates[0])
            return [
                f"    with allure.step('Press key: [{safe_key}]'):\n",
                f"        log.info('Action: press key [{safe_key}]')\n",
                f"        d(label='{first_label}').click()\n",
            ]
        else:
            return [
                f"    with allure.step('Press key: [{safe_key}]'):\n",
                f"        log.info('Action: press key [{safe_key}]')\n",
                f"        d.press('{safe_key.lower()}')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] Press key: '{extra_value}'"


class AssertExistHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        try:
            if platform == "web":
                element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
                is_exist = element.is_visible()
            else:
                is_exist = element.wait(timeout=config.DEFAULT_TIMEOUT)
        except Exception:
            log.warning("❌ [Assert] Element not found / wait timed out — assertion FAILED")
            return False

        if is_exist:
            log.info("[Assert] Passed")
        else:
            log.warning("❌ [Assert] Element not visible — assertion FAILED")
        return bool(is_exist)

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('Assert: element [{l_value}] exists'):\n",
                f"        log.info('Assert: check element [{l_value}] exists')\n",
                "        import playwright.sync_api\n",
                "        try:\n",
                f"            d.{loc_str}.wait_for(state='visible', timeout={timeout * 1000})\n",
                "            is_exist = True\n",
                "        except playwright.sync_api.TimeoutError:\n",
                "            is_exist = False\n",
                "        if not is_exist:\n",
                f"            log.error('Assertion failed: element [{l_value}] not found')\n",
                f"        assert is_exist, 'Assertion failed: element {l_value} not found'\n",
                "        log.info('Assertion passed: element exists')\n",
            ]
        else:
            return [
                f"    with allure.step('Assert: element [{l_value}] exists'):\n",
                f"        log.info('Assert: check element [{l_value}] exists')\n",
                f"        is_exist = d({loc_str}).wait(timeout={timeout})\n",
                "        if not is_exist:\n",
                f"            log.error('Assertion failed: element [{l_value}] not found')\n",
                f"        assert is_exist, 'Assertion failed: element {l_value} not found'\n",
                "        log.info('Assertion passed: element exists')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] Element exists: {l_type}='{l_value}'"


class AssertTextEqualsHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        try:
            if platform == "web":
                element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
                actual_text = element.inner_text().strip()
            else:
                if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                    log.warning("❌ [Assert] Element not found — text assertion FAILED")
                    return False
                actual_text = element.get_text()
        except Exception:
            log.warning("❌ [Assert] Failed to read element text — assertion FAILED")
            return False

        if actual_text != extra_value:
            log.warning(f"❌ [Assert] Expected '{extra_value}', got '{actual_text}' — assertion FAILED")
            return False
        log.info("[Assert] Passed")
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float
    ) -> list:
        safe_expected = _escape_python_string(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value)
        if platform == "web":
            return [
                f"    with allure.step('Assert: text equals [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] text == [{safe_expected}]')\n",
                f"        actual_text = d.{loc_str}.inner_text().strip()\n",
                f"        if actual_text != '{safe_expected}':\n",
                f"            log.error(f'Assertion failed: expected [{safe_expected}], got [{{actual_text}}]')\n",
                f"        assert actual_text == '{safe_expected}', f'Assertion failed: expected {safe_expected}, got {{actual_text}}'\n",
                f"        log.info(f'Assertion passed: text is [{safe_expected}]')\n",
            ]
        else:
            return [
                f"    with allure.step('Assert: text equals [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] text == [{safe_expected}]')\n",
                f"        actual_text = d({loc_str}).get_text()\n",
                f"        if actual_text != '{safe_expected}':\n",
                f"            log.error(f'Assertion failed: expected [{safe_expected}], got [{{actual_text}}]')\n",
                f"        assert actual_text == '{safe_expected}', f'Assertion failed: expected {safe_expected}, got {{actual_text}}'\n",
                f"        log.info(f'Assertion passed: text is [{safe_expected}]')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] Text equals: {l_type}='{l_value}', expected='{extra_value}'"


class GotoHandler(ActionHandler):

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform != "web":
            log.warning("[E034] 'goto' action is only supported on Web platform. Fix: use --platform web")
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
            f"    with allure.step('Navigate to: [{safe_url}]'):\n",
            f"        log.info('Action: navigate to [{safe_url}]')\n",
            f"        d.goto('{safe_url}', wait_until='domcontentloaded')\n",
            "        d.wait_for_timeout(2000)\n",
        ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] Navigate to: {extra_value}"


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
            log.warning("[E035] AI returned empty action type, skipping execution. This usually means the model failed to parse the UI tree correctly.")
            return result

        handler = self._handlers.get(action)
        if not handler:
            log.error(f"[E031] Unsupported action type: '{action}'. Supported: click, input, swipe, press, assert_exist, assert_text_equals, goto, hover, long_click")
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
                log.error("[E032] Element action missing locator_type. Fix: provide --locator-type (css/text/resourceId/description)")
                return result

            u2_locator_map = {
                "resourceId": "resourceId",
                "text": "text",
                "description": "description",
                "id": "resourceId",
                "ref": "ref",
            }
            u2_key = u2_locator_map.get(l_type, l_type)

            if u2_key == "ref" and self.platform == "web":
                # Always re-inspect the live page before resolving a web ref.
                # The ref cache is a process-global; under the long-lived MCP
                # server it would otherwise serve stale @N from a previous page
                # or request (the old `not _cached_ui_elements` guard skipped
                # refresh once anything was cached). compress_web_dom assigns @N
                # by ordinal, so a fresh inspect keeps @N aligned with the page
                # the agent is actually looking at.
                try:
                    import json as _json

                    from utils.utils_web import compress_web_dom
                    ui_json = compress_web_dom(self.d)
                    tree = _json.loads(ui_json)
                    set_ui_elements(tree.get("ui_elements", []))
                    log.info(f"🔍 [Ref] Refreshed ref cache from live page: {len(_cached_ui_elements)} elements")
                except Exception as e:
                    log.warning(f"⚠️ [Ref] Live re-inspect failed, using existing cache: {e}")

            try:
                element = get_actual_element(self.d, self.platform, u2_key, l_value)
            except Exception as e:
                log.warning(f"⚠️ [Warning] Element locator resolution failed: {e}")
                return result

            if element is None and u2_key == "ref" and self.platform == "web":
                el_data = _resolve_ref(l_value)
                if el_data and el_data.get("w", 0) > 0:
                    cx = el_data["x"] + el_data["w"] // 2
                    cy = el_data["y"] + el_data["h"] // 2
                    log.info(f"🎯 [Ref] {l_value} using coordinate fallback: ({cx}, {cy})")
                    try:
                        self.d.mouse.click(cx, cy)
                        code_lines = [
                            f"    with allure.step('Click: [{l_value}] (coordinate)'):\n",
                            f"        log.info('Action: click [{l_value}] at ({cx}, {cy})')\n",
                            f"        d.mouse.click({cx}, {cy})  # ref {l_value} coordinate fallback\n",
                        ]
                        result["success"] = True
                        result["code_lines"] = code_lines
                        result["action_description"] = f"🎯 [Ref] Click {l_value} at ({cx}, {cy})"
                        return result
                    except Exception as e:
                        log.error(f"❌ [Error] Coordinate click failed: {e}")
                        return result

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
                        log.info(f"👁️ [Visual Fallback] Using VLM coordinates: ({cx}, {cy})")
                        self.d.mouse.click(cx, cy)
                        code_lines = [
                            f"    with allure.step('Click: [{l_value}] (visual)'):\n",
                            f"        log.info('Action: click [{l_value}] at ({cx}, {cy})')\n",
                            f"        d.mouse.click({cx}, {cy})  # visual fallback\n",
                        ]
                        result["success"] = True
                        result["code_lines"] = code_lines
                        result["action_description"] = f"👁️ [Visual Fallback] Click {l_value} at ({cx}, {cy})"
                        return result
                except Exception as e:
                    log.warning(f"⚠️ [Visual Fallback] Attempt failed: {e}")

            if element is None:
                log.error("[E033] Element locator is empty after resolution. Fix: verify that the target element exists on the current page via inspect_ui")
                return result

        timeout = config.DEFAULT_TIMEOUT

        try:
            log.info(handler.get_log_message(l_type, l_value, extra_value))

            # Use `is not None`, NOT truthiness: android's UiObject is falsy when
            # it currently matches 0 elements, but it's a valid resolved handle —
            # the handler must still run (e.g. assert_exist needs to wait and then
            # report a real failure). Keying on `element` (truthy) would skip
            # execution for an absent android element and wrongly report success.
            if element is not None or action in ("goto", "swipe", "press"):
                if not handler.execute(self.d, element, self.platform, extra_value):
                    if action in ("assert_exist", "assert_text_equals"):
                        # A failed assertion is a verification verdict (the SUT
                        # did not meet the assertion), NOT an engine error. Tag
                        # it so callers / --json can tell the two apart.
                        result["assertion_failed"] = True
                        log.error(
                            f"❌ [Assert] Assertion failed: {action} "
                            f"{l_type}='{l_value}'"
                        )
                    else:
                        log.error(
                            f"❌ [Error] Action blocked or dependent element not found within {timeout}s"
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
            log.error(f"❌ [Execute Error] Exception during execution: {e}")
            return result
