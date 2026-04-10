# ScreenForge Agent Integration Guide

你是上层 Agent（Claude Code / Cursor / Codex 等），ScreenForge 是你的 UI 执行引擎。

**你负责理解需求、分析 UI 树、制定策略。ScreenForge 只负责连接设备、抓取页面结构、执行物理动作、生成代码。**

## 架构速览

```
agent_cli.py          # 兼容入口（6 行 shim），委托给 cli/dispatch.py
cli/                  # 真实分发层：parser / shared / reporter / doctor / modes/
  dispatch.py         # CLI 入口 main()，参数解析后按模式分发
  modes/default.py    # --goal 自主探索循环（不推荐 Agent 使用）
  modes/action.py     # --action 单步执行
  modes/workflow.py   # --workflow 半结构化执行
  tool_protocol_handlers.py  # --tool-stdin / --tool-request / --mcp-server
```

`agent_cli.py` 仍然可用，但它只是 `from cli.dispatch import main` 的薄壳。所有逻辑实现在 `cli/` 包内。

## 首日关键路径（4 步）

### 1. 获取当前页面结构

```bash
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin
```

返回清洗后的 DOM/XML 树（Web 返回 JSON，Android 返回压缩 XML）。**你来分析这棵树，定位目标元素。**

### 2. 下发单步动作

基于你对 UI 树的分析，逐步执行：

```bash
python agent_cli.py --action goto --platform web --extra-value "https://example.com"
python agent_cli.py --action click --platform web --locator-type text --locator-value "Login"
python agent_cli.py --action input --platform web --locator-type css --locator-value "#username" --extra-value "admin"
python agent_cli.py --action press --platform web --extra-value "Enter"
python agent_cli.py --action assert_exist --platform web --locator-type text --locator-value "Dashboard"
```

### 3. 每步执行后重新 inspect_ui，确认状态

```bash
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin
```

观察页面是否变化，决定下一步。失败时分析退出码和日志，调整策略。

### 4. 验证生成的脚本

```bash
pytest test_cases/web/test_xxx.py
```

### 进阶：使用 workflow 批量执行

当你有多个确定性步骤时，写一个 YAML workflow 一次执行：

```bash
python agent_cli.py --workflow ./my_workflow.yaml --output "test_cases/test_login.py" --platform web
```

可搭配 `--plan-only`（只看计划）、`--dry-run`（只模拟不执行）做预检。

## 支持的 action 类型

| action | 说明 | 需要 locator | 需要 extra_value |
|--------|------|:---:|:---:|
| `goto` | 导航到 URL（仅 Web） | 否 | URL |
| `click` | 点击元素 | 是 | 否 |
| `long_click` | 长按元素 | 是 | 否 |
| `hover` | 悬停（仅 Web） | 是 | 否 |
| `input` | 输入文本 | 是 | 输入内容 |
| `swipe` | 滑动屏幕 | 否 | up/down/left/right |
| `press` | 模拟按键 | 否 | 按键名(Enter/Back) |
| `assert_exist` | 断言元素存在 | 是 | 否 |
| `assert_text_equals` | 断言文本一致 | 是 | 期望文本 |

`locator_type` 优先级：`css` > `resourceId` > `text` > `description`

## 元素定位能力

- **ref 系统 (@N)**：`inspect_ui` 返回的元素自带 `ref` 编号（@1, @2...），可直接用 `--locator-type ref --locator-value @3` 定位
- **bbox 坐标**：每个元素附带 `x, y, w, h` 边界框，用于坐标点击或视觉比对
- **截图标注**：`--vision` 模式下自动生成带 ref 标注的截图，辅助视觉定位
- **视觉 fallback (VLM)**：当 DOM/XML 无法定位目标时（Canvas、游戏等），引擎调用 VLM 从截图中解析坐标

## 工具协议入口

除了直接 shell 调用，还支持机器可读协议：

| 入口 | 用法 |
|------|------|
| `--tool-stdin` | `echo '{"operation":"inspect_ui","platform":"web"}' \| python agent_cli.py --tool-stdin` |
| `--tool-request` | `python agent_cli.py --tool-request ./request.json` |
| `--mcp-server` | `python agent_cli.py --mcp-server`（stdio MCP server） |

支持的 operation：`capabilities`、`inspect_ui`、`load_case_memory`、`execute`、`load_run`

## 排障

- **退出码 0**：成功，脚本已生成到 `--output` 路径
- **退出码 1**：失败，读终端日志中的 `⚠️` 和 `❌`
  - "UI 僵死"：动作执行了但页面没变化，补充前置条件后重试
  - "触发熔断"：连续失败次数达阈值，收窄步骤或加 `--vision`
- **禁止盲目重试相同参数**

## 禁止事项

1. **禁止使用 `--goal`**：该入口会调第三方 LLM 替你思考，浪费 token 且效果差
2. **禁止凭空编写 UI 代码**：你看不到真实画面，必须先 `inspect_ui` 拿到 DOM 树再定位
3. **禁止把自然语言原样透传**：你负责理解需求，ScreenForge 只负责执行动作
