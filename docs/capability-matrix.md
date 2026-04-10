# ScreenForge Capability Matrix

本文档描述当前仓库中已经落地并验证过的能力边界。若上层 Agent 需要机器可读版本，请直接执行 `python agent_cli.py --capabilities`；若需要机器可读执行入口，可使用 `--tool-request`、`--tool-stdin` 或 `--mcp-server`。

## 平台支持总览

| 平台 | 连接能力 | 页面结构采集 | 截图 | 物理动作执行 | 视频/状态产物 | 当前成熟度 |
|---|---|---|---|---|---|---|
| Android | `uiautomator2` | XML 压缩 | 支持 | 支持 | `scrcpy` 录像 | 高 |
| iOS | `facebook-wda` | 暂未实现结构压缩 | 支持 | 基础支持 | 暂无原生录像 | 低 |
| Web | Playwright + CDP | DOM 压缩 | 支持 | 支持 | Playwright 视频 + storage state | 中 |

## 元素定位能力

| 能力 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| ref 编号 (@N) | 支持 | 支持 | 支持 | `inspect_ui` 返回的每个可交互元素自带 ref 编号，可直接用于定位 |
| bbox 坐标 (x,y,w,h) | 支持 | 支持 | 支持 | 每个元素附带边界框坐标，用于坐标点击或视觉比对 |
| 截图标注 | 支持 | 支持 | 支持 | `--vision` 模式下自动生成带 ref 标注的截图，方便上层 Agent 或 VLM 识别 |
| 视觉 fallback (VLM) | 支持 | 支持 | 支持 | DOM/XML 无法定位时（Canvas、游戏、自绘 UI），调用 VLM 从截图解析坐标 |
| css 选择器 | 不适用 | 不适用 | 支持 | Web 端首选定位方式 |
| resourceId | 支持 | 部分支持 | 不适用 | Android 原生 resource-id |
| text / description | 支持 | 支持 | 支持 | 跨平台通用，按可见文本或无障碍描述定位 |

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
| `assert_exist` | 支持 | 基础支持 | 支持 | |
| `assert_text_equals` | 支持 | 基础支持 | 支持 | |

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
