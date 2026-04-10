---
name: operate-android
description: Control Android device for UI automation and test recording. Use when the user asks to tap elements, fill forms, swipe screens, or run Android UI test flows.
disable-model-invocation: false
user-invocable: true
allowed-tools: Bash(python agent_cli.py *) Bash(source .venv/bin/activate *) Bash(echo *) Bash(adb *)
argument-hint: "[goal description]"
---

# ScreenForge Android Automation Skill

**你是大脑，ScreenForge 是手脚。** 你负责理解意图、分析 UI、做决策；ScreenForge 只负责执行单步动作。

> `agent_cli.py` 是 6 行 shim，真实逻辑在 `cli/` 包内。

## 前置条件

- Android 设备已通过 USB 连接，USB 调试已开启
- `adb devices` 可以看到设备
- 已执行 `python -m uiautomator2 init` 推送 ATX 守护进程

快速检查：`source .venv/bin/activate && python agent_cli.py --doctor --platform android`

## 核心工作流

每一步操作都遵循：**inspect → analyze → action → verify** 循环。

### Step 1: 获取当前 UI 状态

```bash
source .venv/bin/activate && echo '{"operation":"inspect_ui","platform":"android"}' | python agent_cli.py --tool-stdin
```

返回压缩后的 XML 树（Token 消耗降低 80%+）。每个可交互元素带有：
- **ref 编号** (@1, @2...) — 直接用于定位
- **bbox 坐标** (x, y, w, h) — 用于坐标点击或视觉比对

**自己分析** XML 树定位目标元素。

### Step 2: 执行动作

根据你从 XML 树中分析出的元素信息，发送精确的动作指令：

```bash
source .venv/bin/activate && python agent_cli.py \
  --platform android \
  --action click --locator-type text --locator-value "Login" \
  --output test_cases/android/test_xxx.py
```

### Step 3: 验证结果

再次运行 Step 1 的 `inspect_ui` 确认操作成功，然后进行下一步。

## 支持的动作类型

| action | 说明 | locator_type | extra_value |
|--------|------|-------------|-------------|
| `click` | 点击元素 | `resourceId`/`text`/`description`/`ref` | - |
| `long_click` | 长按元素 | `resourceId`/`text`/`description`/`ref` | - |
| `input` | 输入文本 | `resourceId`/`text`/`ref` | 要输入的文本 |
| `swipe` | 滑动屏幕 | 不需要 | 方向 (up/down/left/right) |
| `press` | 按键 | 不需要 | 键名 (Back/Enter/Home) |
| `assert_exist` | 断言元素存在 | `resourceId`/`text`/`description`/`ref` | - |
| `assert_text_equals` | 断言文本内容 | `resourceId`/`text`/`ref` | 期望文本 |

`locator_type` 优先级：`resourceId` > `text` > `description` > `ref`

## Android 特有机制

### XML 压缩
- 引擎自动清洗 Android XML 树，剔除系统噪音、独立符号和冗余节点
- Token 消耗降低 80%+，响应更快、成本更低

### Scrcpy 录像
- 测试执行时自动通过 scrcpy 录制视频
- 失败用例的视频自动挂载到 Allure 报告

### 脚本追加模式
- 所有步骤指向同一个 `--output` 文件
- 已有文件时自动追加新步骤，生成连贯的测试脚本

### 视觉 fallback
- `--vision` 模式下自动生成带 ref 标注的截图
- 当 XML 无法定位目标时（游戏、自绘 UI），引擎调用 VLM 从截图解析坐标

## 禁止事项

1. **禁止使用 `--goal` 参数** — 那会调用第三方 LLM 做决策，而你自己才是大脑
2. **禁止凭空编写 uiautomator2 代码** — 必须先 `inspect_ui` 获取真实 XML
3. **禁止把自然语言透传给 ScreenForge** — 你分析，它执行
4. **禁止猜测 resource-id** — 如果 inspect_ui 没返回目标元素，先滑动或等待

## 常见陷阱

- **权限弹窗**: 首次安装后可能弹出权限请求，需要先点"允许"
- **输入法遮挡**: 输入文本后键盘可能遮挡下方元素，用 `press Back` 收起键盘后再操作
- **动态 resource-id**: 部分控件的 resource-id 带随机后缀，优先用 `text` 或 `description` 定位
- **加载延迟**: 网络请求后的页面刷新需要等待，执行动作前先 inspect_ui 确认元素已出现
