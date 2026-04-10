---
name: operate-web
description: Control web browser for UI automation and test recording. Use when the user asks to open a website, click elements, fill forms, navigate pages, or run web UI test flows.
disable-model-invocation: false
user-invocable: true
allowed-tools: Bash(python agent_cli.py *) Bash(source .venv/bin/activate *) Bash(echo *)
argument-hint: "[goal description or URL]"
---

# ScreenForge Web Automation Skill

**你是大脑，ScreenForge 是手脚。** 你负责理解意图、分析 UI、做决策；ScreenForge 只负责执行单步动作。

> `agent_cli.py` 是 6 行 shim，真实逻辑在 `cli/` 包内。

## 核心工作流

每一步操作都遵循：**inspect → analyze → action → verify** 循环。

### Step 1: 启动浏览器并导航

```bash
source .venv/bin/activate && python agent_cli.py \
  --platform web --action goto --extra-value "https://target-url.com" \
  --output test_cases/web/test_xxx.py
```

### Step 2: 获取当前 UI 状态

```bash
source .venv/bin/activate && echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin
```

返回 JSON 包含 `ui_json`（DOM 树）和可选的 `screenshot_base64`。每个可交互元素带有：
- **ref 编号** (@1, @2...) — 直接用于定位
- **bbox 坐标** (x, y, w, h) — 用于坐标点击或视觉比对

**自己分析** DOM 树定位目标元素。

### Step 3: 执行动作

根据你从 DOM 树中分析出的元素信息，发送精确的动作指令：

```bash
source .venv/bin/activate && python agent_cli.py \
  --platform web \
  --action click --locator-type text --locator-value "Login" \
  --output test_cases/web/test_xxx.py
```

### Step 4: 验证结果

再次运行 Step 2 的 `inspect_ui` 确认操作成功，然后进行下一步。

## 支持的动作类型

| action | 说明 | locator_type | extra_value |
|--------|------|-------------|-------------|
| `goto` | 导航到 URL | 不需要 | 目标 URL |
| `click` | 点击元素 | `text`/`css`/`ref` | - |
| `input` | 输入文本 | `text`/`css`/`ref` | 要输入的文本 |
| `hover` | 悬停元素 | `text`/`css`/`ref` | - |
| `press` | 按键 | 不需要 | 键名 (Enter/Tab/Escape) |
| `swipe` | 滚动 | 不需要 | 方向 (up/down/left/right) |
| `assert_exist` | 断言元素存在 | `text`/`css`/`ref` | - |
| `assert_text_equals` | 断言文本内容 | `text`/`css`/`ref` | 期望文本 |

`locator_type` 优先级：`css` > `text` > `ref`

## Web 特有机制

### 持久浏览器 Session
- 浏览器以独立 Chromium 进程运行（CDP 端口 9333），不随 CLI 退出而关闭
- 后续调用自动 reconnect 到已有浏览器，保持页面状态和登录态
- 无需每步都重新打开浏览器

### 脚本追加模式
- 所有步骤指向同一个 `--output` 文件
- 已有文件时自动追加新步骤，生成连贯的测试脚本
- 第一次调用创建文件头和框架，后续追加 `allure.step` 块

### 超时配置
- `DEFAULT_TIMEOUT=30`（秒），Playwright 隐式等待最多 30s
- SPA 网站需要足够的渲染时间，5s 远远不够
- 可通过 `.env` 中 `DEFAULT_TIMEOUT` 覆盖

### 视觉 fallback
- `--vision` 模式下自动生成带 ref 标注的截图
- 当 DOM 无法定位目标时（Canvas、游戏、自绘 UI），引擎调用 VLM 从截图解析坐标

## 禁止事项

1. **禁止使用 `--goal` 参数** — 那会调用第三方 LLM 做决策，而你自己才是大脑
2. **禁止凭空编写 Playwright 代码** — 必须先 `inspect_ui` 获取真实 DOM
3. **禁止把自然语言透传给 ScreenForge** — 你分析，它执行
4. **禁止猜测 UI 元素** — 如果 inspect_ui 没返回目标元素，先滚动或等待

## 常见陷阱

- **CAPTCHA/Bot 检测**: Playwright Chromium 可能被识别为自动化，直接导航到目标网站而非通过搜索引擎
- **元素不可见**: SPA 页面可能需要滚动或等待异步加载，用 `swipe down` 翻页后重新 inspect
- **JSON 解析失败**: inspect_ui 返回的 DOM 可能含控制字符，对 JSON 做容错处理
- **多个同名元素**: 使用 `css` 做更精确的定位，而非 `text`
