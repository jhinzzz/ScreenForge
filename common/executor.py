from abc import ABC, abstractmethod

import config.config as config
from common.capabilities import ASSERTION_ACTIONS, GLOBAL_ACTIONS
from common.error_codes import format_log
from common.logs import log

# NOTE: the web ref cache (@N -> element) lives on the UIExecutor INSTANCE
# (see UIExecutor.set_ui_elements / resolve_ref), not as a module global. A
# process-global cache leaked refs across pages/requests under the long-lived
# MCP server; binding it to the executor the SharedAdapterManager owns per
# platform keeps each session's @N aligned with the page it inspected. The
# ref-aware helpers below therefore take an explicit `resolve_ref` callable
# (default None) instead of reaching for ambient state.


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


def _escape_css_ident(value: str) -> str:
    """Escape a CSS identifier (for an #id selector) per CSS.escape rules: any
    char that isn't [A-Za-z0-9_-] or non-ASCII is backslash-escaped, and a
    leading digit is escaped too. Keeps `locator('#weird.id')` from being parsed
    as id+class."""
    s = str(value)
    out = []
    for ch in s:
        if ch.isalnum() or ch in "_-" or ord(ch) >= 0x80:
            out.append(ch)
        else:
            out.append("\\" + ch)
    result = "".join(out)
    if result and result[0].isdigit():
        result = "\\3" + result[0] + " " + result[1:]
    return result


def _normalize_ws(value: str) -> str:
    """Collapse all whitespace runs to single spaces and trim ends — matches
    Playwright expect().to_have_text / to_contain_text normalization. Keeping the
    live execute() verdict on the SAME normalization as the generated expect()
    code means the autonomous loop never accepts a step the emitted test would
    reject (or vice-versa) over internal whitespace differences."""
    return " ".join(str(value or "").split())


# Map a compressed-DOM element (tag + clickable + type) to an ARIA role, so a
# coordinate fallback can emit a stable get_by_role locator instead of a pixel.
def _infer_web_role(el: dict) -> str | None:
    tag = str(el.get("class", "")).lower()
    el_type = str(el.get("type", "")).lower()
    if tag == "a":
        return "link"
    if tag == "button" or el_type in ("submit", "button", "reset"):
        return "button"
    if el_type == "checkbox":
        return "checkbox"
    if el_type == "radio":
        return "radio"
    if tag == "select":
        return "combobox"
    if tag == "textarea" or (tag == "input" and el_type in ("", "text", "email", "search", "url", "tel", "password")):
        return "textbox"
    return None


def _inner_strategy(el: dict) -> tuple | None:
    """The role/accessible-name/text part of the stability ranking, WITHOUT the
    unique-by-spec id/name attrs and WITHOUT scope. Factored out so the scoped
    and unscoped paths share one source of truth for "how do I name this control"
    — the scoped locator wraps exactly this inner strategy."""
    role = _infer_web_role(el)
    accessible_name = el.get("desc") or el.get("text")
    if role and accessible_name:
        return ("role", role, accessible_name)
    if el.get("desc"):
        return ("label", el["desc"])
    if el.get("placeholder"):
        return ("placeholder", el["placeholder"])
    if el.get("text"):
        return ("text", el["text"])
    return None


def _fallback_strategy(el: dict) -> tuple | None:
    """Decide the single most-stable locator strategy for a web element, by
    uniqueness/stability (architect adc8c2c): id > name attr > scope+inner >
    role+accessible-name > aria-label(desc) > placeholder > text. Returns a
    (kind, *args) tuple or None when nothing locatable exists. Shared by
    build_fallback_locator (codegen string) and get_fallback_element (live
    handle) so the EMITTED locator and the one we actually click can never
    diverge.

    `name`/`id` rank above role+name because they're unique by spec; a role+name
    match can be duplicated on a page (the "wrong element" trap). When the
    compressor flagged the element as ambiguous (`scope` = its row's identifying
    text), we wrap the inner role/text strategy in that scope instead of falling
    into the silent `.first` trap — Playwright strict-mode then fails loud if the
    scope still isn't unique."""
    if not el:
        return None
    if el.get("id"):
        # CSS.escape-equivalent for an #id selector; bare ids with special chars
        # would otherwise build a malformed selector.
        return ("css", f"#{_escape_css_ident(el['id'])}")
    if el.get("name"):
        # Escape backslash+double-quote so a name containing " can't prematurely
        # close the [name="..."] attribute selector.
        safe_name = str(el["name"]).replace("\\", "\\\\").replace('"', '\\"')
        return ("css", f'[name="{safe_name}"]')
    inner = _inner_strategy(el)
    # Ambiguous control (one of N same-named) → scope by its row's identifying
    # text. Only meaningful when there IS an inner strategy to scope.
    scope = el.get("scope")
    if scope and inner:
        return ("scoped", str(scope), *inner)
    # Known-ambiguous (compressor set dup_index → it was in a >=2 collision group)
    # but no usable scope: refuse to emit a flat inner locator, which would carry a
    # silent `.first` and always hit row 1 (the lie). Return None so the caller
    # takes the honest pytest.skip path instead of persisting a wrong-row test.
    if el.get("dup_index") is not None and inner:
        return None
    return inner


def _inner_locator_frag(strat: tuple) -> str | None:
    """Render an inner (role/label/placeholder/text) strategy tuple to a
    Playwright locator fragment WITHOUT a trailing `.first` — so it can be either
    suffixed with `.first` (flat, unscoped) or chained after a scope (no `.first`,
    strict-mode enforces uniqueness within the row)."""
    kind = strat[0]
    if kind == "css":
        return f"locator('{_escape_locator_value(strat[1])}')"
    if kind == "role":
        return f"get_by_role('{strat[1]}', name='{_escape_locator_value(strat[2])}')"
    if kind == "label":
        return f"get_by_label('{_escape_locator_value(strat[1])}')"
    if kind == "placeholder":
        return f"get_by_placeholder('{_escape_locator_value(strat[1])}')"
    if kind == "text":
        return f"get_by_text('{_escape_locator_value(strat[1])}')"
    return None


def build_fallback_locator(el: dict) -> str | None:
    """Best-effort STABLE Playwright locator EXPRESSION for a web element when
    the @N ref chain (id → text) didn't resolve. Returns e.g.
    "get_by_role('button', name='Save').first", or None when the element has no
    locatable attribute (the pure-coordinate / visual-fallback shape). A
    coordinate is NEVER returned — callers that get None must skip, not click a
    pixel.

    For an ambiguous control (one of N same-named, carrying `scope`), returns a
    SCOPED locator — get_by_text('<row label>').locator('..').<inner> with NO
    `.first` — so the persisted test targets the right row instead of silently
    clicking row 1."""
    strat = _fallback_strategy(el)
    if strat is None:
        return None
    if strat[0] == "scoped":
        # ("scoped", scope_text, *inner_strategy)
        scope_text, inner = strat[1], strat[2:]
        inner_frag = _inner_locator_frag(inner)
        if inner_frag is None:
            return None
        # Scope to the row by its identifying text, hop to the row container
        # (`..`), then locate the control within it. exact=True so a scope that is
        # a SUBSTRING of another row's label (e.g. "Bob" vs "Bob Jones") doesn't
        # match both — Playwright get_by_text defaults to substring matching. No
        # `.first`: if the scope still isn't unique, strict-mode fails loud, never
        # silently row 1.
        return f"get_by_text('{_escape_locator_value(scope_text)}', exact=True).locator('..').{inner_frag}"
    inner_frag = _inner_locator_frag(strat)
    return f"{inner_frag}.first" if inner_frag is not None else None


def _inner_locator_handle(scope, strat: tuple):
    """Live Playwright handle for an inner strategy tuple, rooted at `scope` (a
    locator/frame). Twin of _inner_locator_frag — same strategy, live handle —
    so the emitted string and the clicked handle can never diverge."""
    kind = strat[0]
    if kind == "css":
        return scope.locator(strat[1])
    if kind == "role":
        return scope.get_by_role(strat[1], name=strat[2])
    if kind == "label":
        return scope.get_by_label(strat[1])
    if kind == "placeholder":
        return scope.get_by_placeholder(strat[1])
    if kind == "text":
        return scope.get_by_text(strat[1])
    return None


def get_fallback_element(d, el: dict):
    """Live Playwright locator for the SAME strategy build_fallback_locator
    emits, so the runtime block can click the element it will write into the
    test (not a pixel) and prove the locator actually resolves. Returns a
    locator handle or None."""
    strat = _fallback_strategy(el)
    if strat is None:
        return None
    if strat[0] == "scoped":
        scope_text, inner = strat[1], strat[2:]
        # exact=True mirrors the emitted string — substring scope ("Bob" in
        # "Bob Jones") must not match both. No `.first`: strict-mode enforces it.
        row = d.get_by_text(scope_text, exact=True).locator("..")
        handle = _inner_locator_handle(row, inner)
        return handle
    handle = _inner_locator_handle(d, strat)
    return handle.first if handle is not None else None


def readable_ref_target(el: dict | None) -> str:
    """Human-readable label for a web @N element (text → desc → name → id),
    falling back to the ref token itself so a label is never empty."""
    if not el:
        return ""
    return el.get("text") or el.get("desc") or el.get("name") or el.get("id") or el.get("ref", "")


def humanize_step_labels(code_lines: list, ref_token: str, readable: str) -> list:
    """Replace a raw `[@N]` ref token with a human-readable target inside the
    generated allure.step / log lines. Pure transform: only rewrites the bracket
    token `[@N]`, never the resolved locator call (which already uses real
    text/id). No-op when the token isn't present or `readable` is empty."""
    if not ref_token or not readable or f"[{ref_token}]" not in "".join(code_lines):
        return code_lines
    return [line.replace(f"[{ref_token}]", f"[{readable}]") for line in code_lines]


class LocatorBuilder:
    @staticmethod
    def build_code(platform: str, u2_key: str, l_value: str, resolve_ref=None) -> str:
        safe_val = _escape_locator_value(l_value)
        if platform == "web":
            if u2_key == "ref":
                el_data = resolve_ref(l_value) if resolve_ref else None
                if el_data:
                    # Stable-locator chain (id → name → scope → role → label →
                    # placeholder → text). NEVER a coordinate: a pixel click baked
                    # into a persisted test rots silently on any layout shift.
                    fragment = build_fallback_locator(el_data)
                    if fragment:
                        return fragment
                    # build_fallback_locator returned None. For a KNOWN-AMBIGUOUS
                    # ref (dup_index set, no usable scope) emit the bare name WITHOUT
                    # `.first` — strict-mode then fails loud on the ambiguity instead
                    # of silently clicking row 1. (In normal flow the live side
                    # resolves to None first and the caller emits pytest.skip; this
                    # is the honest string if build_code is reached directly.)
                    if el_data.get("dup_index") is not None:
                        name = el_data.get("desc") or el_data.get("text") or ""
                        if name:
                            return f"get_by_text('{_escape_locator_value(name)}')"
                    # No locatable attribute at all → a literal that fails loud
                    # at replay (better than a silently-rotting coordinate).
                    return f"locator('{safe_val}').first"
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
    def get_element(d, platform: str, u2_key: str, l_value: str, resolve_ref=None):
        if platform == "web":
            if u2_key == "ref":
                el_data = resolve_ref(l_value) if resolve_ref else None
                if not el_data:
                    log.warning(f"[E030] Ref {l_value} not found in cache. Fix: run inspect_ui first to refresh the element cache")
                    return None
                if el_data.get("id"):
                    return d.locator(f"#{el_data['id']}").first
                # Defer to the SHARED strategy (the same one build_fallback_locator
                # emits) instead of a private get_by_text(...).first chain — so a
                # scoped/ambiguous ref resolves live to the SAME element we persist,
                # and an unscopable-ambiguous ref resolves to None (→ honest skip)
                # rather than silently clicking row 1.
                return get_fallback_element(d, el_data)
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


def build_locator_code(platform: str, u2_key: str, l_value: str, resolve_ref=None) -> str:
    return LocatorBuilder.build_code(platform, u2_key, l_value, resolve_ref=resolve_ref)


def get_actual_element(d, platform: str, u2_key: str, l_value: str, resolve_ref=None):
    return LocatorBuilder.get_element(d, platform, u2_key, l_value, resolve_ref=resolve_ref)


class ActionHandler(ABC):
    @abstractmethod
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        pass

    @abstractmethod
    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
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
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
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
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
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
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
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
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        safe_extra = _escape_python_string(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
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
    _DIRECTIONS = ("up", "down", "left", "right")

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        direction = extra_value.lower() if extra_value else "down"
        if direction not in self._DIRECTIONS:
            direction = "down"
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
        elif platform == "ios":
            # facebook-wda has no swipe_ext (that's uiautomator2/Android). It
            # exposes directional swipe_up/down/left/right() on the client.
            getattr(d, f"swipe_{direction}")()
        else:
            d.swipe_ext(direction)
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        direction = extra_value.lower() if extra_value else "down"
        if direction not in self._DIRECTIONS:
            direction = "down"
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
            ]
        elif platform == "ios":
            return [
                f"    with allure.step('Swipe: [{direction}]'):\n",
                f"        log.info('Action: swipe [{direction}]')\n",
                f"        d.swipe_{direction}()\n",
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
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        key = extra_value if extra_value else "Enter"
        safe_key = _escape_python_string(key)
        if platform == "web":
            # No trailing sleep in generated code: the next action's locator
            # auto-waits. (The live execute() path keeps a brief settle because
            # it feeds a screenshot to the LLM before any next action exists.)
            return [
                f"    with allure.step('Press key: [{safe_key}]'):\n",
                f"        log.info('Action: press key [{safe_key}]')\n",
                f"        d.keyboard.press('{safe_key}')\n",
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
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
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
                actual_text = element.inner_text()
            else:
                if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                    log.warning("❌ [Assert] Element not found — text assertion FAILED")
                    return False
                actual_text = element.get_text()
        except Exception:
            log.warning("❌ [Assert] Failed to read element text — assertion FAILED")
            return False

        # Normalize whitespace so this live verdict matches the generated
        # expect().to_have_text (which normalizes) — see _normalize_ws.
        if _normalize_ws(actual_text) != _normalize_ws(extra_value):
            log.warning(f"❌ [Assert] Expected '{extra_value}', got '{actual_text}' — assertion FAILED")
            return False
        log.info("[Assert] Passed")
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        safe_expected = _escape_python_string(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        if platform == "web":
            # Playwright's expect(...).to_have_text auto-retries until the text
            # matches or the timeout elapses — eliminates the read-once race the
            # old inner_text() comparison had on async-updating UIs.
            return [
                f"    with allure.step('Assert: text equals [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] text == [{safe_expected}]')\n",
                "        from playwright.sync_api import expect\n",
                f"        expect(d.{loc_str}).to_have_text('{safe_expected}', timeout={timeout * 1000})\n",
                f"        log.info('Assertion passed: text is [{safe_expected}]')\n",
            ]
        else:
            return [
                f"    with allure.step('Assert: text equals [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] text == [{safe_expected}]')\n",
                f"        assert d({loc_str}).wait(timeout={timeout}), 'Assertion failed: element {l_value} not found'\n",
                f"        actual_text = d({loc_str}).get_text()\n",
                f"        assert actual_text == '{safe_expected}', f'Assertion failed: expected {safe_expected}, got {{actual_text}}'\n",
                f"        log.info(f'Assertion passed: text is [{safe_expected}]')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] Text equals: {l_type}='{l_value}', expected='{extra_value}'"


class AssertTextContainsHandler(ActionHandler):
    """Assert an element's text CONTAINS a substring (not exact equality)."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        try:
            if platform == "web":
                element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
                actual_text = element.inner_text()
            else:
                if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                    log.warning("❌ [Assert] Element not found — text-contains assertion FAILED")
                    return False
                actual_text = element.get_text()
        except Exception:
            log.warning("❌ [Assert] Failed to read element text — assertion FAILED")
            return False

        # Normalize whitespace on both sides so this matches the generated
        # expect().to_contain_text (which normalizes) — see _normalize_ws.
        if _normalize_ws(extra_value) not in _normalize_ws(actual_text):
            log.warning(f"❌ [Assert] '{extra_value}' not found in '{actual_text}' — assertion FAILED")
            return False
        log.info("[Assert] Passed")
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        safe_expected = _escape_python_string(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        if platform == "web":
            return [
                f"    with allure.step('Assert: text contains [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] text contains [{safe_expected}]')\n",
                "        from playwright.sync_api import expect\n",
                f"        expect(d.{loc_str}).to_contain_text('{safe_expected}', timeout={timeout * 1000})\n",
                f"        log.info('Assertion passed: text contains [{safe_expected}]')\n",
            ]
        else:
            return [
                f"    with allure.step('Assert: text contains [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] text contains [{safe_expected}]')\n",
                f"        assert d({loc_str}).wait(timeout={timeout}), 'Assertion failed: element {l_value} not found'\n",
                f"        actual_text = d({loc_str}).get_text()\n",
                f"        assert '{safe_expected}' in (actual_text or ''), f'Assertion failed: [{safe_expected}] not in [{{actual_text}}]'\n",
                f"        log.info('Assertion passed: text contains [{safe_expected}]')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] Text contains: {l_type}='{l_value}', substring='{extra_value}'"


class AssertNotExistHandler(ActionHandler):
    """Assert an element is absent / hidden (the negative of assert_exist)."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform == "web":
            try:
                element.wait_for(state="hidden", timeout=config.DEFAULT_TIMEOUT * 1000)
                log.info("[Assert] Passed (element hidden/absent)")
                return True
            except Exception:
                log.warning("❌ [Assert] Element still visible — assert_not_exist FAILED")
                return False
        else:
            # uiautomator2's UiObject exposes wait_gone (verified present).
            if element.wait_gone(timeout=config.DEFAULT_TIMEOUT):
                log.info("[Assert] Passed (element gone)")
                return True
            log.warning("❌ [Assert] Element still present — assert_not_exist FAILED")
            return False

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        if platform == "web":
            return [
                f"    with allure.step('Assert: element [{l_value}] absent'):\n",
                f"        log.info('Assert: check element [{l_value}] is hidden/absent')\n",
                "        from playwright.sync_api import expect\n",
                f"        expect(d.{loc_str}).to_be_hidden(timeout={timeout * 1000})\n",
                f"        log.info('Assertion passed: element [{l_value}] absent')\n",
            ]
        else:
            return [
                f"    with allure.step('Assert: element [{l_value}] absent'):\n",
                f"        log.info('Assert: check element [{l_value}] is gone')\n",
                f"        gone = d({loc_str}).wait_gone(timeout={timeout})\n",
                f"        assert gone, 'Assertion failed: element {l_value} still present'\n",
                f"        log.info('Assertion passed: element [{l_value}] absent')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] Element absent: {l_type}='{l_value}'"


class AssertValueHandler(ActionHandler):
    """Assert a form field's value.

    Web reads the true field value via Playwright `input_value()`. On mobile
    there is no generic "field value" accessor, so this asserts the element's
    `text` — which for an Android `EditText` IS the entered value, but for other
    widgets (or an empty field showing a hint) may be the placeholder/label. Use
    `assert_value` for input fields on mobile; for arbitrary text use
    `assert_text_equals` / `assert_text_contains`."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        try:
            if platform == "web":
                element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
                actual = element.input_value()
            else:
                if not element.wait(timeout=config.DEFAULT_TIMEOUT):
                    log.warning("❌ [Assert] Element not found — value assertion FAILED")
                    return False
                actual = element.get_text()
        except Exception:
            log.warning("❌ [Assert] Failed to read element value — assertion FAILED")
            return False

        if actual != extra_value:
            log.warning(f"❌ [Assert] Expected value '{extra_value}', got '{actual}' — assertion FAILED")
            return False
        log.info("[Assert] Passed")
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        safe_expected = _escape_python_string(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        if platform == "web":
            return [
                f"    with allure.step('Assert: value equals [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] value == [{safe_expected}]')\n",
                "        from playwright.sync_api import expect\n",
                f"        expect(d.{loc_str}).to_have_value('{safe_expected}', timeout={timeout * 1000})\n",
                f"        log.info('Assertion passed: value is [{safe_expected}]')\n",
            ]
        else:
            return [
                f"    with allure.step('Assert: value equals [{safe_expected}]'):\n",
                f"        log.info('Assert: check [{l_value}] value == [{safe_expected}]')\n",
                f"        assert d({loc_str}).wait(timeout={timeout}), 'Assertion failed: element {l_value} not found'\n",
                f"        actual_value = d({loc_str}).get_text()\n",
                f"        assert actual_value == '{safe_expected}', f'Assertion failed: expected {safe_expected}, got {{actual_value}}'\n",
                f"        log.info(f'Assertion passed: value is [{safe_expected}]')\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] Value equals: {l_type}='{l_value}', expected='{extra_value}'"


class AssertUrlHandler(ActionHandler):
    """Global web assertion: the page URL contains the expected substring."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform != "web":
            log.warning("[Assert] assert_url is only supported on Web platform")
            return False
        try:
            actual_url = d.url
        except Exception:
            log.warning("❌ [Assert] Failed to read page URL — assertion FAILED")
            return False
        if extra_value not in (actual_url or ""):
            log.warning(f"❌ [Assert] '{extra_value}' not in URL '{actual_url}' — assertion FAILED")
            return False
        log.info("[Assert] Passed")
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        import re as _re
        safe_expected = _escape_python_string(extra_value)
        # to_have_url accepts a regex; embed the substring as an escaped pattern
        # so it matches anywhere in the URL and auto-retries until navigation lands.
        pattern = _re.escape(extra_value)
        safe_pattern = _escape_python_string(pattern)
        return [
            f"    with allure.step('Assert: URL contains [{safe_expected}]'):\n",
            f"        log.info('Assert: check URL contains [{safe_expected}]')\n",
            "        import re\n",
            "        from playwright.sync_api import expect\n",
            f"        expect(d).to_have_url(re.compile('{safe_pattern}'), timeout={timeout * 1000})\n",
            f"        log.info('Assertion passed: URL contains [{safe_expected}]')\n",
        ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Assert] URL contains: '{extra_value}'"


class WaitForHandler(ActionHandler):
    """Explicit synchronization: wait until an element is visible (default) or
    hidden. extra_value selects the state: "" / "visible" / "appear" → visible;
    "hidden" / "gone" / "disappear" → hidden. Replaces magic sleeps."""

    _HIDDEN_WORDS = ("hidden", "gone", "disappear", "absent")
    _VISIBLE_WORDS = ("", "visible", "appear", "shown", "present")

    def _wants_hidden(self, extra_value: str) -> bool:
        token = str(extra_value or "").strip().lower()
        if token in self._HIDDEN_WORDS:
            return True
        if token not in self._VISIBLE_WORDS:
            log.debug(
                f"[Wait] Unrecognized state '{extra_value}', defaulting to 'visible' "
                f"(use one of {self._HIDDEN_WORDS} for a hidden-wait)"
            )
        return False

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        hidden = self._wants_hidden(extra_value)
        if platform == "web":
            state = "hidden" if hidden else "visible"
            try:
                element.wait_for(state=state, timeout=config.DEFAULT_TIMEOUT * 1000)
                log.info(f"[Wait] Condition met (state={state})")
                return True
            except Exception:
                log.warning(f"❌ [Wait] Timed out waiting for state={state}")
                return False
        else:
            if hidden:
                ok = element.wait_gone(timeout=config.DEFAULT_TIMEOUT)
            else:
                ok = element.wait(timeout=config.DEFAULT_TIMEOUT)
            if ok:
                log.info("[Wait] Condition met")
                return True
            log.warning("❌ [Wait] Timed out")
            return False

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        hidden = self._wants_hidden(extra_value)
        loc_str = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        if platform == "web":
            state = "hidden" if hidden else "visible"
            return [
                f"    with allure.step('Wait for [{l_value}] ({state})'):\n",
                f"        log.info('Wait: [{l_value}] -> {state}')\n",
                f"        d.{loc_str}.wait_for(state='{state}', timeout={timeout * 1000})\n",
            ]
        else:
            call = f"wait_gone(timeout={timeout})" if hidden else f"wait(timeout={timeout})"
            return [
                f"    with allure.step('Wait for [{l_value}]'):\n",
                f"        log.info('Wait: [{l_value}]')\n",
                f"        assert d({loc_str}).{call}, 'Wait condition not met for {l_value}'\n",
            ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Wait] {l_type}='{l_value}', state='{extra_value or 'visible'}'"


class GotoHandler(ActionHandler):

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if platform != "web":
            log.warning("[E034] 'goto' action is only supported on Web platform. Fix: use --platform web")
            return False
        url = extra_value.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        d.goto(url, wait_until="load", timeout=config.DEFAULT_TIMEOUT * 1000)
        return True

    def generate_code(
        self, platform: str, u2_key: str, l_value: str, extra_value: str, timeout: float,
        resolve_ref=None,
    ) -> list:
        url = extra_value.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        safe_url = _escape_python_string(url)
        # goto(wait_until='load') is itself a synchronization point (it waits for
        # the load event). No trailing sleep: the NEXT action's locator
        # auto-waits, which is Playwright's recommended readiness strategy.
        # (networkidle is explicitly discouraged by Playwright for testing.)
        return [
            f"    with allure.step('Navigate to: [{safe_url}]'):\n",
            f"        log.info('Action: navigate to [{safe_url}]')\n",
            f"        d.goto('{safe_url}', wait_until='load')\n",
        ]

    def get_log_message(self, l_type: str, l_value: str, extra_value: str) -> str:
        return f"[Action] Navigate to: {extra_value}"


def _web_only(action_label: str, platform: str) -> bool:
    """These interactions have a clean, stable Playwright API but no robust
    coordinate-free equivalent on uiautomator2/wda, and P2 deliberately stopped
    emitting coordinate-based code. Engage only on web; elsewhere fail honestly
    (not a silent skip) so the caller knows the action wasn't performed."""
    if platform == "web":
        return True
    log.warning(f"⚠️ [Action] '{action_label}' is web-only; not supported on {platform}")
    return False


def _autodetect_web_target(d, value: str):
    """Resolve a secondary target (e.g. a drag destination) from a bare string:
    a value starting with #/./[ is treated as a css selector, anything else as
    visible text. (Mirrors _target_locator_code so live and codegen agree.)"""
    v = str(value).strip()
    if v.startswith(("#", ".", "[")):
        return d.locator(v).first
    return d.get_by_text(v).first


def _target_locator_code(value: str) -> str:
    v = str(value).strip()
    if v.startswith(("#", ".", "[")):
        return f"locator('{_escape_locator_value(v)}').first"
    return f"get_by_text('{_escape_locator_value(v)}').first"


class ScrollIntoViewHandler(ActionHandler):
    """Scroll an element into the viewport (element-targeted, not blind swipe)."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if not _web_only("scroll_into_view", platform):
            return False
        try:
            element.scroll_into_view_if_needed(timeout=config.DEFAULT_TIMEOUT * 1000)
            return True
        except Exception:
            log.warning("❌ [Action] scroll_into_view timed out")
            return False

    def generate_code(self, platform, u2_key, l_value, extra_value, timeout, resolve_ref=None) -> list:
        loc = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        return [
            f"    with allure.step('Scroll into view: [{l_value}]'):\n",
            f"        log.info('Action: scroll [{l_value}] into view')\n",
            f"        d.{loc}.scroll_into_view_if_needed(timeout={timeout * 1000})\n",
        ]

    def get_log_message(self, l_type, l_value, extra_value) -> str:
        return f"[Action] Scroll into view: {l_type}='{l_value}'"


class SelectHandler(ActionHandler):
    """Select an <option> in a native <select> by its label/value."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if not _web_only("select", platform):
            return False
        try:
            element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
            element.select_option(extra_value, timeout=config.DEFAULT_TIMEOUT * 1000)
            return True
        except Exception as e:
            log.warning(f"❌ [Action] select_option('{extra_value}') failed: {e}")
            return False

    def generate_code(self, platform, u2_key, l_value, extra_value, timeout, resolve_ref=None) -> list:
        loc = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        safe = _escape_python_string(extra_value)
        return [
            f"    with allure.step('Select [{safe}] in [{l_value}]'):\n",
            f"        log.info('Action: select [{safe}] in [{l_value}]')\n",
            f"        d.{loc}.select_option('{safe}', timeout={timeout * 1000})\n",
        ]

    def get_log_message(self, l_type, l_value, extra_value) -> str:
        return f"[Action] Select: {l_type}='{l_value}', option='{extra_value}'"


class UploadHandler(ActionHandler):
    """Set a file <input>'s files (file upload). extra_value is the file path."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if not _web_only("upload", platform):
            return False
        try:
            # No wait_for(visible): file <input>s are routinely display:none
            # (styled label over a hidden input); set_input_files targets hidden
            # inputs by design, so a visibility wait would wrongly break it.
            element.set_input_files(extra_value, timeout=config.DEFAULT_TIMEOUT * 1000)
            return True
        except Exception as e:
            log.warning(f"❌ [Action] set_input_files('{extra_value}') failed: {e}")
            return False

    def generate_code(self, platform, u2_key, l_value, extra_value, timeout, resolve_ref=None) -> list:
        loc = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        safe = _escape_python_string(extra_value)
        return [
            f"    with allure.step('Upload [{safe}] to [{l_value}]'):\n",
            f"        log.info('Action: upload [{safe}] to [{l_value}]')\n",
            f"        d.{loc}.set_input_files('{safe}', timeout={timeout * 1000})\n",
        ]

    def get_log_message(self, l_type, l_value, extra_value) -> str:
        return f"[Action] Upload: {l_type}='{l_value}', file='{extra_value}'"


class DoubleClickHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if not _web_only("double_click", platform):
            return False
        try:
            element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
            element.dblclick(timeout=config.DEFAULT_TIMEOUT * 1000)
            return True
        except Exception as e:
            log.warning(f"❌ [Action] dblclick failed: {e}")
            return False

    def generate_code(self, platform, u2_key, l_value, extra_value, timeout, resolve_ref=None) -> list:
        loc = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        return [
            f"    with allure.step('Double click: [{l_value}]'):\n",
            f"        log.info('Action: double click [{l_value}]')\n",
            f"        d.{loc}.dblclick(timeout={timeout * 1000})\n",
        ]

    def get_log_message(self, l_type, l_value, extra_value) -> str:
        return f"[Action] Double click: {l_type}='{l_value}'"


class RightClickHandler(ActionHandler):
    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if not _web_only("right_click", platform):
            return False
        try:
            element.wait_for(state="visible", timeout=config.DEFAULT_TIMEOUT * 1000)
            element.click(button="right", timeout=config.DEFAULT_TIMEOUT * 1000)
            return True
        except Exception as e:
            log.warning(f"❌ [Action] right click failed: {e}")
            return False

    def generate_code(self, platform, u2_key, l_value, extra_value, timeout, resolve_ref=None) -> list:
        loc = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        return [
            f"    with allure.step('Right click: [{l_value}]'):\n",
            f"        log.info('Action: right click [{l_value}]')\n",
            f"        d.{loc}.click(button='right', timeout={timeout * 1000})\n",
        ]

    def get_log_message(self, l_type, l_value, extra_value) -> str:
        return f"[Action] Right click: {l_type}='{l_value}'"


class DragHandler(ActionHandler):
    """Drag the source element onto a target. The source is the action's
    locator; the target is extra_value, auto-detected (css if #/./[ else text)."""

    def execute(self, d, element, platform: str, extra_value: str) -> bool:
        if not _web_only("drag", platform):
            return False
        if not str(extra_value).strip():
            log.warning("❌ [Action] drag requires a target in extra_value")
            return False
        try:
            target = _autodetect_web_target(d, extra_value)
            element.drag_to(target, timeout=config.DEFAULT_TIMEOUT * 1000)
            return True
        except Exception as e:
            log.warning(f"❌ [Action] drag_to failed: {e}")
            return False

    def generate_code(self, platform, u2_key, l_value, extra_value, timeout, resolve_ref=None) -> list:
        loc = build_locator_code(platform, u2_key, l_value, resolve_ref=resolve_ref)
        target_loc = _target_locator_code(extra_value)
        safe_target = _escape_python_string(extra_value)
        return [
            f"    with allure.step('Drag [{l_value}] to [{safe_target}]'):\n",
            f"        log.info('Action: drag [{l_value}] to [{safe_target}]')\n",
            f"        d.{loc}.drag_to(d.{target_loc}, timeout={timeout * 1000})\n",
        ]

    def get_log_message(self, l_type, l_value, extra_value) -> str:
        return f"[Action] Drag: {l_type}='{l_value}' to '{extra_value}'"


class UIExecutor:
    def __init__(self, device, platform="android"):
        self.d = device
        self.platform = platform
        # Web ref cache (@N -> element), bound to THIS instance. The
        # SharedAdapterManager keeps one executor per platform, so an inspect_ui
        # and a follow-up `ref @N` action in the same MCP session share this
        # cache while separate sessions/pages can never leak into each other.
        self._cached_ui_elements: list[dict] = []
        self._handlers = {
            "click": ClickHandler(),
            "long_click": LongClickHandler(),
            "hover": HoverHandler(),
            "input": InputHandler(),
            "swipe": SwipeHandler(),
            "press": PressHandler(),
            "goto": GotoHandler(),
            "scroll_into_view": ScrollIntoViewHandler(),
            "select": SelectHandler(),
            "upload": UploadHandler(),
            "double_click": DoubleClickHandler(),
            "right_click": RightClickHandler(),
            "drag": DragHandler(),
            "wait_for": WaitForHandler(),
            "assert_exist": AssertExistHandler(),
            "assert_not_exist": AssertNotExistHandler(),
            "assert_text_equals": AssertTextEqualsHandler(),
            "assert_text_contains": AssertTextContainsHandler(),
            "assert_value": AssertValueHandler(),
            "assert_url": AssertUrlHandler(),
        }

    def set_ui_elements(self, elements: list[dict]) -> None:
        self._cached_ui_elements = list(elements) if elements else []

    def resolve_ref(self, ref_value: str) -> dict | None:
        for el in self._cached_ui_elements:
            if el.get("ref") == ref_value:
                return el
        return None

    def _recover_web_ref(self, handler, action, l_value, extra_value, result: dict) -> dict:
        """Web @N ref that get_actual_element couldn't resolve. Try, in order:
        a recovered stable locator (re-driven through the action's own handler),
        then a live coordinate click for `click` only (persisted as a skip, never
        a rotting coordinate). Always terminal — returns the result dict."""
        el_data = self.resolve_ref(l_value)
        # The id→text chain in get_actual_element missed this ref, but the
        # element dict may still carry name/role/desc/placeholder. Recover
        # the SAME stable locator we'd emit (build_fallback_locator) as a
        # LIVE handle and re-drive the action's own handler on it — so an
        # input stays an input, a hover stays a hover, etc. The handler's
        # execute() validates the locator resolves (discharges the "locator
        # points at a different element than the pixel" trap) and its
        # generate_code() persists that stable locator — never a pixel.
        fb_element = get_fallback_element(self.d, el_data) if el_data else None
        if fb_element is not None and build_fallback_locator(el_data):
            try:
                if handler.execute(self.d, fb_element, self.platform, extra_value):
                    # generate_code with u2_key="ref" + the live resolve_ref
                    # rebuilds the SAME stable fragment build_fallback_locator
                    # produced (build_code's ref branch calls it) — so the
                    # persisted locator exactly matches the handle we just
                    # acted on. Then humanize the [@N] labels to readable.
                    code_lines = handler.generate_code(
                        self.platform, "ref", l_value, extra_value,
                        config.DEFAULT_TIMEOUT, resolve_ref=self.resolve_ref,
                    )
                    readable = readable_ref_target(el_data)
                    if readable and readable != l_value:
                        code_lines = humanize_step_labels(code_lines, l_value, readable)
                    result["success"] = True
                    result["code_lines"] = code_lines
                    result["action_description"] = (
                        f"🔁 [Ref] {action} {l_value} via recovered locator"
                    )
                    return result
                log.warning(f"⚠️ [Ref] Recovered locator did not satisfy {action}")
            except Exception as e:
                log.warning(f"⚠️ [Ref] Recovered locator failed to act: {e}")
        # No stable locator. Act LIVE via coordinate ONLY for click (the
        # sole action a bare coordinate can perform) so a recording session
        # still advances; persist an honest, non-passing skip rather than a
        # silently-rotting coordinate. For non-click actions there is
        # nothing a coordinate can do — report a real engine failure.
        if action == "click" and el_data and el_data.get("w", 0) > 0:
            cx = el_data["x"] + el_data["w"] // 2
            cy = el_data["y"] + el_data["h"] // 2
            try:
                self.d.mouse.click(cx, cy)
                log.info(f"🎯 [Ref] {l_value} clicked at ({cx}, {cy}) live (not persisted)")
            except Exception as e:
                log.error(f"❌ [Error] Coordinate click failed: {e}")
                return result
            log.warning(
                f"[E036] Ref {l_value} has no stable locator (only coordinates). "
                f"Emitting pytest.skip so the test isn't silently green."
            )
            code_lines = [
                f"    with allure.step('Click: [{l_value}] (UNREPLAYABLE)'):\n",
                "        import pytest\n",
                f"        # Ref {l_value} could only be located by coordinate at record time;\n",
                "        # no durable selector exists. Provide one before treating this as real.\n",
                f"        pytest.skip('Ref {l_value} has no durable locator (coordinate-only at record time)')\n",
            ]
            result["success"] = True
            result["code_lines"] = code_lines
            result["action_description"] = f"⏭️ [Ref] {l_value} unreplayable — skip emitted"
            return result
        log.error(format_log("E037") + f" (ref={l_value}, action='{action}')")
        result["error_code"] = "E037"
        return result

    def _try_visual_fallback(self, l_type, l_value, result: dict) -> dict | None:
        """VLM screenshot-coordinate click recovery (web click only). Returns the
        result dict on a hit (persisted as a skip — a VLM point has no durable
        locator), or None to fall through to the standard not-found path."""
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
                # Click live so the session advances, but the visual
                # fallback has NO DOM node — only a VLM screenshot hit —
                # so there is no durable locator to emit. Persist a skip
                # (with the coordinate kept as a comment hint) rather than
                # a coordinate that will rot and pass green against the
                # wrong pixel later.
                self.d.mouse.click(cx, cy)
                code_lines = [
                    f"    with allure.step('Click: [{l_value}] (UNREPLAYABLE: visual)'):\n",
                    "        import pytest\n",
                    f"        # Located only via VLM screenshot at ({cx}, {cy}); no DOM locator exists.\n",
                    f"        # d.mouse.click({cx}, {cy})  # original visual hit, reference only\n",
                    f"        pytest.skip('Visual-fallback step for [{l_value}] has no durable locator; add a selector to make it replayable')\n",
                ]
                result["success"] = True
                result["code_lines"] = code_lines
                result["action_description"] = f"⏭️ [Visual Fallback] {l_value} unreplayable — skip emitted"
                return result
        except Exception as e:
            log.warning(f"⚠️ [Visual Fallback] Attempt failed: {e}")
        return None

    def execute_and_record(self, action_data: dict, file_obj=None) -> dict:
        action = action_data.get("action")
        l_type = action_data.get("locator_type", "global")
        l_value = action_data.get("locator_value", "global")
        extra_value = action_data.get("extra_value", "")

        result = {
            "success": False,
            "code_lines": [],
            "action_description": "",
            "error_code": "",
            "action_info": {
                "action_type": action,
                "locator_type": l_type,
                "locator_value": l_value,
                "extra_value": extra_value,
            },
        }

        if not action:
            log.warning(format_log("E035"))
            result["error_code"] = "E035"
            return result

        handler = self._handlers.get(action)
        if not handler:
            log.error(format_log("E031"))
            result["error_code"] = "E031"
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
                log.error(format_log("E032"))
                result["error_code"] = "E032"
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
                # compress_web_dom assigns @N by ordinal, so a fresh inspect
                # keeps @N aligned with the page the agent is actually looking
                # at. The cache is bound to this executor instance (not a
                # process-global), so the refresh can't bleed into another
                # session.
                try:
                    import json as _json

                    from utils.utils_web import compress_web_dom
                    ui_json = compress_web_dom(self.d)
                    tree = _json.loads(ui_json)
                    self.set_ui_elements(tree.get("ui_elements", []))
                    log.info(f"🔍 [Ref] Refreshed ref cache from live page: {len(self._cached_ui_elements)} elements")
                except Exception as e:
                    log.warning(f"⚠️ [Ref] Live re-inspect failed, using existing cache: {e}")

            try:
                element = get_actual_element(
                    self.d, self.platform, u2_key, l_value, resolve_ref=self.resolve_ref
                )
            except Exception as e:
                log.warning(f"⚠️ [Warning] Element locator resolution failed: {e}")
                return result

            if element is None and u2_key == "ref" and self.platform == "web":
                return self._recover_web_ref(handler, action, l_value, extra_value, result)

            # Visual fallback can only CLICK (a VLM returns a point, nothing
            # else) — never engage it for input/hover/assert/etc.
            if element is None and self.platform == "web" and action == "click":
                recovered = self._try_visual_fallback(l_type, l_value, result)
                if recovered is not None:
                    return recovered

            if element is None:
                log.error(format_log("E033"))
                result["error_code"] = "E033"
                return result

        timeout = config.DEFAULT_TIMEOUT

        try:
            log.info(handler.get_log_message(l_type, l_value, extra_value))

            # Use `is not None`, NOT truthiness: android's UiObject is falsy when
            # it currently matches 0 elements, but it's a valid resolved handle —
            # the handler must still run (e.g. assert_exist needs to wait and then
            # report a real failure). Keying on `element` (truthy) would skip
            # execution for an absent android element and wrongly report success.
            if element is not None or action in GLOBAL_ACTIONS:
                if not handler.execute(self.d, element, self.platform, extra_value):
                    if action in ASSERTION_ACTIONS:
                        # A failed assertion is a verification verdict (the SUT
                        # did not meet the assertion), NOT an engine error. Tag
                        # it so callers / --json can tell the two apart.
                        result["assertion_failed"] = True
                        log.error(
                            f"❌ [Assert] Assertion failed: {action} "
                            f"{l_type}='{l_value}'"
                        )
                    else:
                        log.error(format_log("E038"))
                        result["error_code"] = "E038"
                    return result

            safe_u2_key = u2_key if needs_locator else ""
            code_lines = handler.generate_code(
                self.platform, safe_u2_key, l_value, extra_value, timeout,
                resolve_ref=self.resolve_ref,
            )

            # Single choke point for readable allure.step labels: when a web ref
            # (@N) was used, the locator line already carries the resolved
            # text/id, but the step/log labels still say "[@N]". Swap the bracket
            # token for the human-readable target so reports read cleanly.
            if self.platform == "web" and safe_u2_key == "ref":
                readable = readable_ref_target(self.resolve_ref(l_value))
                if readable and readable != l_value:
                    code_lines = humanize_step_labels(code_lines, l_value, readable)

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
