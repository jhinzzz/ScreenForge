# ScreenForge Capability Matrix

本文档描述当前仓库中已经落地并验证过的能力边界。若上层 Agent 需要机器可读版本，请直接执行 `python agent_cli.py --capabilities`；若需要机器可读执行入口，可使用 `--tool-request`、`--tool-stdin` 或 `--mcp-server`。

## 平台支持总览

| 平台 | 连接能力 | 页面结构采集 | 截图 | 物理动作执行 | 视频/状态产物 | 当前成熟度 |
|---|---|---|---|---|---|---|
| Android | `uiautomator2` | XML 压缩 | 支持 | 支持 | `scrcpy` 录像 | 高 |
| iOS | `facebook-wda` | 暂未实现结构压缩 | 支持 | 基础支持 | 暂无原生录像 | 低 |
| Web | Playwright + CDP | DOM 压缩（穿透 open shadow DOM + 同源 iframe） | 支持 | 支持 | Playwright 视频 + storage state | 中 |

> ℹ️ **Web DOM 压缩器穿透能力（2026-06）**：`compress_web_dom` 递归遍历 open shadow
> DOM 与同源/`srcdoc` iframe，iframe 内元素的 bbox 会按 iframe 的位置 + 边框 + 内边距
> 偏移回顶层坐标，保证 ref/坐标点击不错位。**不可交互判定**（均仍收录便于断言，但标
> `clickable:false`，避免 LLM 去点死元素卡超时）：
> - `disabled` / `aria-disabled` 控件 → `disabled:true`；用 `:disabled` 伪类判定，
>   故 `<fieldset disabled>` 传播给后代控件（含首个 `<legend>` 内豁免、嵌套继承）也覆盖。
> - `inert` 子树（开 `<dialog>` 时背景标 inert 的标准模式）→ 独立的 `inert:true` 字段
>   （**不**当作 `disabled`，二者语义不同），且 inert 状态会跨 shadow / 同源 iframe 边界继承。
>
> **不可穿透**：closed shadow root、跨域 iframe（浏览器安全边界，静默跳过）。

## 元素定位能力

> ⚠️ **ref / bbox / 截图标注 / 视觉 fallback 仅 Web 端可用。** 移动端的 UI 树压缩器
> (`utils_xml.py` / `utils_ios.py`) 不产出 ref 编号或 bbox 坐标，视觉 fallback 在
> `executor.py` 也只对 `platform == "web"` 生效。机器可读版本见
> `python agent_cli.py --capabilities` 的 `locators` / `features` 字段。

| 能力 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| ref 编号 (@N) | 不支持 | 不支持 | 支持 | 仅 `compress_web_dom` 为每个 Web 元素分配 ref；移动端不产出 |
| bbox 坐标 (x,y,w,h) | 不支持 | 不支持 | 支持 | 仅 Web 元素附带边界框坐标，用于坐标点击或视觉比对 |
| 截图标注 | 不支持 | 不支持 | 支持 | `--vision` 模式下仅 Web 自动生成带 ref 标注的截图 |
| 视觉 fallback (VLM) | 不支持 | 不支持 | 支持 | 仅 Web：DOM 无法定位时调用 VLM 从截图解析坐标（`executor.py` 内 gate 在 web） |
| css 选择器 | 不适用 | 不适用 | 支持 | Web 端首选定位方式 |
| resourceId | 支持 | 映射到 name | 不适用 | Android 原生 resource-id；iOS 映射到 `name` |
| text / description | 支持 | 支持（映射到 label） | 支持 | 跨平台通用，按可见文本或无障碍描述定位 |

## CLI 模式支持

| 模式 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| `run` | 支持 | 基础支持 | 支持 | 默认自主探索并生成 pytest 脚本 |
| `action` | 支持 | 基础支持 | 支持 | 单步即时动作执行 |
| `workflow` | 支持 | 基础支持 | 支持 | 半结构化 YAML 工作流执行 |
| `doctor` | 支持 | 支持 | 支持 | 只检查环境与前置条件 |
| `plan-only` | 支持 | 基础支持 | 支持 | 生成执行前计划，不执行物理动作 |
| `dry-run` | 支持 | 基础支持 | 支持 | 走决策链输出 would-execute 结果，不执行物理动作 |
| `resume-run-id` | 支持 | 支持 | 支持 | 从已有 run report 恢复最小上下文 |
| `mcp-server` | 支持 | 支持 | 支持 | 以 stdio 方式暴露最小 MCP tools 接口 |

## 人类入口与 Agent 入口分工

| 入口 | 面向对象 | 是否允许自然语言直接驱动 | 是否允许内部第三方 LLM 推理 | 推荐用途 |
|---|---|---|---|---|
| `main.py` | 人类 | 允许 | 允许 | 自然语言调试、交互式录制 |
| `agent_cli.py --action/--workflow` | Agent / 研发 | 不推荐 | 不需要 | 结构化执行、排障、代码生成 |
| `--tool-request` / `--tool-stdin` / `--mcp-server` | Agent | 不允许 | 不允许 | `inspect_ui -> load_case_memory -> execute` |

> `agent_cli.py` 是 6 行 shim，所有逻辑实现在 `cli/` 包内。

## 已落地动作类型

| 动作 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| `click` | 支持 | 基础支持 | 支持 | 标准点击 |
| `long_click` | 支持 | 基础支持 | 通过延迟 click 模拟 | |
| `hover` | 忽略 | 忽略 | 支持 | 仅 Web 真正生效 |
| `input` | 支持 | 基础支持 | 支持 | |
| `swipe` | 支持 | 依赖底层能力 | 支持 | Web 通过滚轮模拟 |
| `press` | 支持 | 基础支持 | 支持 | |
| `scroll_into_view` | 不适用 | 不适用 | 支持 | 仅 Web：元素级滚动进视口（优于盲目 swipe）。移动端无稳健的免坐标等价实现 |
| `select` | 不适用 | 不适用 | 支持 | 仅 Web：原生 `<select>` 选项选择。`extra_value` = 选项文本或 value |
| `upload` | 不适用 | 不适用 | 支持 | 仅 Web：文件 `<input>` 上传。`extra_value` = 文件路径 |
| `double_click` | 不适用 | 不适用 | 支持 | 仅 Web：双击 |
| `right_click` | 不适用 | 不适用 | 支持 | 仅 Web：右键（触发上下文菜单） |
| `drag` | 不适用 | 不适用 | 支持 | 仅 Web：拖拽。locator 定位源，`extra_value` = 目标(css 或文本)。指针式拖拽；HTML5 dataTransfer 原生 DnD 不在覆盖范围 |
| `wait_for` | 支持 | 基础支持 | 支持 | 显式同步：等待元素出现/消失，替代死等。`extra_value` = `visible`(默认)/`hidden` |
| `assert_exist` | 支持 | 基础支持 | 支持 | 元素出现（Web 端 `wait_for(visible)` 自动轮询） |
| `assert_not_exist` | 支持 | 基础支持 | 支持 | 元素消失/不存在（Web `to_be_hidden`、Android `wait_gone`） |
| `assert_text_equals` | 支持 | 基础支持 | 支持 | 文本完全相等（Web 端用 `expect().to_have_text` 自动重试） |
| `assert_text_contains` | 支持 | 基础支持 | 支持 | 文本包含子串（动态文本首选，Web `expect().to_contain_text`） |
| `assert_value` | 支持 | 基础支持 | 支持 | 表单字段值（Web `expect().to_have_value`、移动端取 text） |
| `assert_url` | 不适用 | 不适用 | 支持 | 仅 Web：页面 URL 含子串（global 动作，`expect().to_have_url` 自动重试） |

> ℹ️ **Web 断言采用 Playwright `expect()` 自动重试**：生成的测试代码对文本/值/可见性断言使用 `expect(locator).to_*(..., timeout=...)`，会轮询至条件满足或超时，消除异步 UI 上"读一次就比较"的 flaky。`execute()` 实时裁决路径保持有界轮询返回布尔值，供自治循环与 `--json` 区分"断言失败"与"引擎错误"。`goto/press/swipe` 生成代码不再写入固定 `wait_for_timeout` 死等——`goto` 用 `wait_until='load'` 同步，后续动作依赖定位器自身的 auto-wait。

## 自愈引擎

| 能力 | 状态 | 说明 |
|---|---|---|
| 结构化 JSON 输出 | 已落地 | `HealResult` dataclass，返回 `confidence / fix_description / fixed_code` |
| 4 策略 JSON 解析 | 已落地 | 直接 JSON → JSON fence → 平衡括号提取 → markdown code block → 原文 fallback |
| AST 语法校验 | 已落地 | `ast.parse(fixed_code)` 验证，语法错误则 confidence=0.0 |
| 置信度阈值 | 已落地 | 低于 `AUTO_HEAL_MIN_CONFIDENCE`（默认 0.7）时跳过自愈 |
| 覆盖前备份 | 已落地 | `shutil.copy2` 生成 `.bak` 文件后再覆盖测试脚本 |

## 当前已知边界

1. `APP_ENV_CONFIG` 当前仓库默认只配置了 `dev` 环境，其他环境需用户自行补充。
2. iOS 目前只具备基础接入能力，尚未实现和 Android / Web 同等级的结构采集、录像和启动流程。
3. Web 当前依赖已启动的 Chrome CDP 会话，使用前需要准备好 `WEB_CDP_URL`。
4. `plan-only` 和 `dry-run` 是控制面能力，重点是预览与排障，不替代正式 `run` 模式。
5. `mcp-server` 当前暴露 `ui_agent_capabilities`、`ui_agent_inspect_ui`、`ui_agent_load_case_memory`、`ui_agent_execute` 和 `ui_agent_load_run` 五个 tools。
6. 视觉 fallback (VLM) 依赖 `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL_NAME` 配置，未配置时自动降级到纯 DOM/XML 定位。
7. 真正的 `run` 执行完成后，会自动更新 `memory/case_memory.json`，供后续 Agent 运行复用测试资产。
