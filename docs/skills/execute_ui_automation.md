# Tool / Skill: execute_ui_automation (ScreenForge 多端 UI 自动化探索引擎)

## 描述 (Description)

这是 `ScreenForge` 提供的底层视觉驱动与跨端 UI 自动化探索引擎。作为主控 Agent，你无法直接看到设备的屏幕画面，也无法精确猜测 UI 元素的定位（如 resource-id 或 xpath）。因此，当你需要执行任何 UI 自动化、真机操作或测试用例生成任务时，**必须**通过在终端执行该命令来下发任务，由底层引擎代为探索。

## 执行命令 (CLI Command)

```python
python agent_cli.py --goal "<测试目标>" --output "<代码保存路径>" [其他参数]
```

## 参数列表 (Arguments)

- `-goal` (必填, string): 一句话清晰描述业务流程和终点。**必须包含操作流程和最终的预期断言**。例如：`"登录账号admin密码123，并断言出现工作台字样"`。
- `-output` (必填, string): 生成的 pytest 脚本的存放路径。必须以 `test_` 开头，例如：`"test_cases/test_login.py"`。
- `-platform` (可选, string): 测试目标平台。可选值：`android` (默认), `ios`, `web`。
- `-vision` (可选, flag): 开启多模态视觉辅助。**强烈建议：当目标包含复杂图形、自绘UI、游戏界面或常规DOM结构缺失时，必须加上此参数 `-vision`**。
- `-context` (可选, string): 指向一个本地的 `.txt` 或 `.md` 文件路径。如果任务包含复杂 PRD、特定业务规则或长文本测试账号，请先将其写入一个临时文件，再将文件路径传给此参数。
- `-max_retries` (可选, int): 单步最大连续错误重试次数。默认 `3`。
- `-max_steps` (可选, int): 最大允许探索的总步数。默认 `15`。

## 使用约束 (Constraints)

1. **不要伪造测试代码**: 绝不要尝试自己手写 UI 自动化交互代码，因为你极大概率会猜错元素的定位器。请始终把任务外包给本工具。
2. **分析退出状态码 (Exit Code)**:
    - 如果命令退出码为 `0`: 代表探索引擎成功完成目标，代码已生成到 `-output` 指定的路径。你可以运行 `pytest <路径>` 验证。
    - 如果命令退出码为 `1`: 代表引擎遇到了阻塞。你**必须**阅读终端的报错输出（关注 `⚠️` 和 `❌`）。
3. **遇到阻碍如何重试**:
    - 报错 "UI 僵死"：说明点击无效，请补充前置条件（比如先勾选协议）后重试。
    - 报错 "元素未找到"：尝试加上 `-vision` 参数让底层引擎进行视觉分析，或者简化 `-goal` 的描述。
    - **禁止盲目无限重试相同的参数。**

## 示例 (Examples)

**场景 1：执行 Android 登录用例测试**

```python
python agent_cli.py --goal "使用账户 admin 密码 123456 登录系统，并断言页面出现了'工作台'字样" --output "test_cases/test_login.py"
```

**场景 2：针对复杂的 Web H5 画布页面（需要开启视觉）**

```python
python agent_cli.py --goal "在游戏大厅页面找到并点击右上角的红色设置齿轮图标，断言弹出设置菜单" --output "test_cases/test_h5_setting.py" --platform web --vision
```
