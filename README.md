# 🤖 Android AI 自动化测试录制器 (AI-Agent UI Recorder)

这是一个基于大语言模型 (LLM) 和 uiautomator2 的 Android 自动化测试录制工具。通过简单的自然语言对话，AI 即可理解测试意图，自动寻找屏幕元素并执行操作，最终生成符合企业级最佳实践的 Pytest + Allure 测试脚本。

# ✨ 核心特性

🗣️ **自然语言驱动**：输入"点击登录"、"在账号框输入admin"，AI 自动完成元素定位与操作。

⚡ **极致 Token 优化**：内置 Android XML 清洗降维算法，剔除冗余节点，Token 消耗降低 80% 以上，响应更快、成本更低。

🛡️ **智能断言校验**：支持 `assert_exist` 和 `assert_text_equals` 等验证动作，保障测试有效性。

📦 **企业级框架集成**：自动生成带有 `@allure.step` 的标准 `pytest` 脚本，无缝接入 CI/CD。

📸 **失败自动截图**：配合 `conftest.py` 的高级 Hook，断言失败时自动截取手机屏幕并挂载到 Allure 报告中。

🎬 **视频录制功能**：支持使用 scrcpy 自动录制测试执行视频，失败用例视频自动挂载到报告。

🌐 **多平台支持**：支持 Android (uiautomator2)、iOS (WDA)、Web (Playwright) 三大平台自动化测试。

🔧 **多环境配置**：支持 dev、prod、us\_dev、us\_prod 四个环境的 App 配置切换。

# 🛠️ 环境依赖与安装

## 1. 基础要求

- Python 3.8 或以上版本
- 一台 Android 手机（或模拟器），已开启开发者模式和 USB 调试，并通过数据线连接到电脑

## 2. 安装 Python 依赖库

在项目根目录下，执行以下命令安装所需依赖：

```bash
pip install uiautomator2 openai pytest allure-pytest loguru
```

## 3. 初始化 Android 设备

运行以下命令，向手机端推送 uiautomator2 的守护进程（ATX 应用）：

```bash
python -m uiautomator2 init
```

（注：首次执行时，手机上可能会弹出安装提示，请全部点击"允许"或"确认"。）

## 4. 安装 Allure 命令行工具 (用于生成可视化报告)

- macOS: `brew install allure`
- Windows: 使用 Scoop 安装 (`scoop install allure`) 或前往 Allure GitHub Releases 下载解压并配置系统环境变量

## 5. 安装 scrcpy (用于视频录制，可选)

- macOS: `brew install scrcpy`
- Windows: 前往 [scrcpy 官方仓库](https://github.com/Genymobile/scrcpy) 下载

# ⚙️ 配置指南

## 方式一：环境变量配置（推荐）

强烈建议通过环境变量配置，以避免提交代码时泄露敏感信息：

```bash
# 配置 API Key
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# 配置 Base URL（如使用第三方中转）
export OPENAI_BASE_URL="https://api.openai.com/v1"

# 配置模型名称
export MODEL_NAME="gpt-4o"
```

## 方式二：直接修改配置文件

打开 `config/config.py` 文件进行配置：

```python
# config/config.py

# 填入你可用的大模型 API Key (如 OpenAI、通义千问、DeepSeek 等兼容 OpenAI 格式的接口)
OPENAI_API_KEY = "your-api-key-here"

# 如果使用第三方中转或私有部署模型，请修改 Base URL
OPENAI_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 推荐使用推理能力较强的模型，如 gpt-4o, claude-3-5-sonnet 等
MODEL_NAME = "doubao-seed-2-0-lite-260215"

# 全局隐式等待时间（秒），缓解页面异步加载导致的找不到元素问题
DEFAULT_TIMEOUT = 5.0
```

## 环境配置

项目支持多环境切换，修改 `config/config.py` 中的 `APP_ENV_CONFIG`：

```python
APP_ENV_CONFIG = {
    "dev": {
        "android": "",
        "ios": "",
        "web": "",
    }
}
```

# 🚀 快速上手 (使用流程)

## 第一步：启动 AI 录制引擎

确保手机停留在你想测试的 App 页面，在终端运行：

```bash
python main.py
```

## 第二步：交互式生成脚本

终端会提示你输入指令，你可以像聊天一样控制手机：

```bash
👉 请输入自然语言指令 (输入 'q' 退出): 点击"我的"标签页
[System] 抓取并压缩 XML 树...
[Action] 正在等待并点击: text='我的'

👉 请输入自然语言指令 (输入 'q' 退出): 点击右上角的设置图标
[System] 抓取并压缩 XML 树...
[Action] 正在等待并点击: description='设置'

👉 请输入自然语言指令 (输入 'q' 退出): 校验页面上出现了"退出登录"字样
[System] 抓取并压缩 XML 树...
[Assert] 校验元素存在: text='退出登录'
[Assert] ✅ 校验通过

👉 请输入自然语言指令 (输入 'q' 退出): q
🎉 录制结束！
```

## 第三步：回放测试用例

录制结束后，代码已自动生成在 `test_cases/test_auto_generated.py` 中。直接使用 `pytest` 运行（全程不再消耗 AI API 额度）：

```bash
# 运行所有测试用例
pytest

# 运行指定用例
pytest test_cases/test_auto_generated.py

# 指定平台运行（android/ios/web）
pytest --platform=android
```

## 第四步：查看 Allure 测试报告

回放完成后，会在 `./report/allure-results` 目录下生成原始数据。运行以下命令开启可视化报告：

```bash
allure serve ./report/allure-results
```

此时浏览器会自动打开，你可以查看到带有详细执行步骤和（如果失败）错误截图的精美测试报告！

# 📁 项目结构说明

```
ui_agent/
├── main.py                  # AI 录制引擎入口
├── conftest.py              # Pytest 夹具与多平台适配器
├── pytest.ini               # Pytest 运行规则配置
├── config/
│   └── config.py            # 全局配置 (API Keys, 超时, 环境配置)
├── common/
│   ├── ai.py                # AI 交互层：Prompt 构造与 JSON 解析
│   ├── executor.py          # 动作执行器：处理 click/input/assert 操作
│   ├── logs.py              # 日志模块
│   └── adapters/
│       ├── __init__.py        # 导出所有适配器
│       ├── base_adapter.py    # 基础适配器，定义通用接口
│       ├── android_adapter.py # Android uiautomator2 适配器
│       ├── ios_adapter.py     # iOS facebook-wda 适配器
│       └── web_adapter.py     # Web Playwright 适配器
├── utils/
│   └── utils_xml.py         # Android XML 清洗与降维算法
└── test_cases/
    └── test_auto_generated.py  # AI 自动生成的测试用例
```

## 模块说明

| 模块                  | 说明                                       |
| ------------------- | ---------------------------------------- |
| main.py             | 录制引擎入口，负责设备连接、UI 抓取、AI 决策、动作执行           |
| conftest.py         | Pytest 夹具层，提供设备 fixture、失败截图 Hook、跨平台适配器 |
| config/config.py    | 全局配置管理，支持 API Keys、超时时间、多环境 App 配置       |
| common/ai.py        | AI 交互层，构造 Prompt 发送给大模型，解析 JSON 动作指令     |
| common/executor.py  | 动作执行器，实现 click/input/assert 等操作的执行与代码生成  |
| common/logs.py      | 日志模块，基于 loguru 提供统一的日志输出                 |
| utils/utils\_xml.py | XML 清洗降维算法，提取关键交互节点，降低 Token 消耗          |

# ❓ 常见问题 (FAQ)

## Q1: 运行时报错 DeviceNotFoundError 或连接设备失败怎么办？

确保手机已连上 USB 调试。可以使用 `adb devices` 命令查看是否有设备在线。如果有设备，请再次执行 `python -m uiautomator2 init`。

## Q2: 大模型频繁返回乱码或无法解析动作？

检查 config.py 中的 MODEL\_NAME。UI 结构理解需要较强的逻辑推理能力，推荐使用千亿参数级别的旗舰模型。如果是国内大模型，建议使用具有强大代码/JSON 输出能力的模型。

## Q3: 录制时点击了，但脚本回放时找不到元素报错？

可能是由于页面动画或网络加载延迟导致。可以在 config.py 中适当增大 DEFAULT\_TIMEOUT（默认 5.0 秒）以增加容错率。

## Q4: 视频录制功能无法使用？

确保已安装 scrcpy。运行 `scrcpy --version` 验证安装。如果仍然失败，检查手机是否授权了屏幕录制权限。

## Q5: 如何切换测试环境？

目前环境切换需要修改 `config/config.py` 中的 `APP_ENV_CONFIG`，或在代码中调用 `launch_app(device, env_name="prod")` 指定环境。

# 🐛 问题报告指南

## 报告格式

请按以下格式提交问题：

```
## 问题描述
[简洁描述遇到的问题]

## 复现步骤
1. [第一步]
2. [第二步]
3. [第三步]

## 预期行为
[描述你期望发生的行为]

## 实际行为
[描述实际发生的行为]

## 环境信息
- 操作系统: [如 macOS 14.0]
- Python 版本: [如 3.11.5]
- 手机型号: [如 Samsung Galaxy S21]
- 手机系统版本: [如 Android 13]
- 项目版本/提交哈希: [如 abc1234]

## 错误日志
[粘贴完整的错误日志]

## 附加信息
[任何其他有助于解决问题的信息]
```

## 必要信息

请确保提供以下信息：

1. **复现步骤**：清晰的操作步骤，让我们能重现问题
2. **错误日志**：完整的错误信息，包括堆栈跟踪
3. **环境信息**：操作系统、Python 版本、手机型号等
4. **截图/录像**：如果涉及 UI 问题，提供相关截图或录像

## 提交方式

- 邮件: niux520@qq.com

***

感谢你的反馈，我会尽快处理！
