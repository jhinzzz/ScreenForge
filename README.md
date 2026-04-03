# 🤖 Agentic UI Automation Framework (多端/多模态/智能体 UI 自动化引擎)

这是一个基于大语言模型 (LLM) 和多模态视觉 (VLM) 的下一代跨端自动化测试探索与录制框架。

项目已经从单纯的 "Human-in-the-loop" (人在环路交互录制) 进化为 **"Agent-in-the-loop" (智能体底层探索引擎)**。无论是人类通过自然语言聊天录制，还是外部超级 Agent (如 Claude Code, Cursor, AutoGen) 下发宏观指令，本引擎都能自主观察、推理、操作，并最终生成符合企业级最佳实践的 Pytest + Allure 测试脚本。

## ✨ 核心特性

🗣️ **双模式驱动**：

- **交互录制模式**：像聊天一样控制手机，每一步生成标准代码，内置 L1/L2 语义动作缓存省钱提速。
- **Agentic 探索模式**：输入宏观目标（如"登录并验证失败提示"），引擎自主进行多步探索、闭环验证并生成完整脚本。

👁️ **多模态视觉感知 (`--vision`)**：除了原有的 XML 降维清洗算法，还支持实时屏幕截图注入。在面对游戏界面、图表、Canvas 或复杂自绘 UI 时，开启视觉能力让 AI "看"得更准。

🛡️ **自愈与防死循环 (Anti-Stagnation)**：内置 UI 僵死检测和智能熔断机制。遇到"无效点击"或"被遮挡"时，底层引擎会自动向大模型注入反馈，促使其改变策略；连续多次失败或页面卡死才会触发熔断退出，坚决杜绝 Token 浪费。

📦 **跨平台大一统**：底层采用优雅的 Adapter 模式，一键切换操作目标：

- `Android` (uiautomator2)
- `iOS` (facebook-wda)
- `Web` (Playwright)

🎬 **全链路追踪与回放**：自动生成带有 `@allure.step` 的规范代码，支持断言自动失败截图，以及基于 Scrcpy/原生方案的**自动执行视频录制与报告挂载**。

⚡ **极致 Token 优化**：内置 Android XML 清洗降维算法，剔除底层系统噪音、独立符号和巨型冗余节点，Token 消耗降低 80% 以上，响应更快、成本更低。

🧾 **结构化运行产物 (`--json`)**：`agent_cli.py` 支持向 stdout 输出 JSON Lines 事件流，并在 `report/runs/<run_id>/` 下生成 `summary.json`、`steps.jsonl`、`artifacts.json` 和视觉截图索引，便于上层 Agent 或编排系统消费。

## 🛠️ 环境依赖与安装

### 1. 基础要求

- Python 3.10 或以上版本（推荐使用 Python 3.11+）
- 一台 Android 手机（或模拟器），已开启开发者模式和 USB 调试，并通过数据线连接到电脑

### 2. 创建虚拟环境（推荐）

强烈推荐使用虚拟环境隔离项目依赖：

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate
```

### 3. 安装 Python 依赖库

激活虚拟环境后，在项目根目录下执行：

```bash
pip install -r requirement.txt
```

如果你只想手动安装核心依赖，可以执行以下命令：

```bash
pip install uiautomator2 openai pytest allure-pytest loguru filelock numpy sentence-transformers
```

*(注: 若需支持 iOS 或 Web，请自行补充安装 `facebook-wda` 或 `playwright` 依赖)*

### 4. 初始化 Android 设备

运行以下命令，向手机端推送 uiautomator2 的守护进程（ATX 应用）：

```bash
python -m uiautomator2 init
```

*（注：首次执行时，手机上可能会弹出安装提示，请全部点击"允许"或"确认"。)*

### 5. 安装辅助工具 (Allure & Scrcpy)

- **Allure 命令行工具 (用于生成可视化报告)**
    - macOS: `brew install allure`
    - Windows: 使用 Scoop 安装 (`scoop install allure`) 或前往 GitHub Releases 下载配置环境变量。
- **Scrcpy (用于测试回放时的视频录制)**
    - macOS: `brew install scrcpy`
    - Windows: 前往 scrcpy 官方仓库下载。

## ⚙️ 配置指南

强烈建议通过环境变量配置，以避免提交代码时泄露敏感信息，或直接修改 `config/config.py` 文件：

```bash
# 配置 API Key
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# 配置 Base URL（如使用第三方中转）
export OPENAI_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"

# 配置模型名称 (推荐使用推理能力强、支持多模态的旗舰模型)
export MODEL_NAME="doubao-seed-2.0-lite-260215"
```

**多环境配置**：项目支持 dev/prod/us_dev/us_prod 环境的 App 包名与 URL 配置切换，详见 `config/config.py` 中的 `APP_ENV_CONFIG`。

## 🚀 核心工作流一：接入超级 Agent (Agentic Mode)

这是本框架的**终极形态**。你可以将本框架作为底层 Tool/Skill 赋能给 Claude Code, Cursor 等外部超级 Agent。你可以让大模型直接阅读 `docs/AGENT_GUIDE.md` 学习如何调用此引擎。

**典型用法**：
在 Cursor 的 Terminal，或给 Claude Code 下发指令：

> *"请阅读 `docs/AGENT_GUIDE.md`。产品新增了退出登录功能，请帮我自动写一个测试用例，保存为 `test_logout.py`，最后跑一遍 pytest。"*


外部 Agent 会自动调用底层的 CLI 探索引擎：

```bash
python agent_cli.py --goal "进入设置并退出登录，最后断言出现登录按钮" \
                    --output "test_cases/test_logout.py" \
                    --platform android \
                    --vision \
                    --json \
                    --max_retries 3
```

### CLI 核心参数说明

- `-goal`: (必填) 宏观测试目标，必须包含操作流程和最终断言标准。
- `-output`: (可选) 脚本输出的绝对或相对路径。引擎会自动创建平台目录（如 `test_cases/android/`）。
- `-platform`: (可选) 目标平台 (`android` | `ios` | `web`)。
- `-vision`: (可选 Flag) 开启多模态视觉辅助（建议在遇到复杂图形时开启）。
- `-json`: (可选 Flag) 向 stdout 输出 JSON Lines 事件流，供上层 Agent / 编排系统解析。
- `-context`: (可选) 传入包含 PRD、帐号密码等复杂规则的临时 txt/md 文件路径。
- `-max_retries`: (可选) 熔断阈值：单步操作的最大连续容错重试次数，默认 3。

引擎在探测完成后，若成功会以 `Exit Code 0` 退出，失败或熔断则以 `Exit Code 1` 退出，供上层 Agent 捕获并进行自省重试。

### 运行产物

- `report/runs/<run_id>/summary.json`: 本次运行的状态摘要、退出码、输出脚本路径
- `report/runs/<run_id>/steps.jsonl`: 结构化事件流落盘副本
- `report/runs/<run_id>/artifacts.json`: 已生成脚本、截图等产物索引
- `report/runs/<run_id>/screenshots/`: `--vision` 模式下的运行截图

### 迁移者建议先看

- `docs/agent_guide.md`: 给上层 Agent 的集成规范
- `docs/capability-matrix.md`: 平台、动作、定位器支持矩阵与已知边界

## 💻 核心工作流二：人机交互录制 (Interactive Mode)

如果您希望手动、一步一步地把控录制细节，可以启动原汁原味的交互式引擎：

```bash
python main.py
```

终端会提示你输入指令，你可以像聊天一样控制手机：

```
👉 请输入自然语言指令 (输入 'q' 退出): 点击"我的"标签页
[System] 抓取并压缩 XML 树...
[Action] 正在等待并点击: text='我的'

👉 请输入自然语言指令 (输入 'q' 退出): 校验页面上出现了"退出登录"字样
[Assert] 校验元素存在: text='退出登录'
[Assert] ✅ 校验通过

👉 请输入自然语言指令 (输入 'q' 退出): q
🎉 录制结束！
```

此模式下，框架默认开启 **本地 L1/L2 语义缓存 (`CacheManager`)**，相似的 UI 树和指令将实现极速匹配，避免重复消耗大模型 API 费用。同时支持输入 `u` (Undo) 撤销上一步操作。

### Interactive Mode 快捷指令

- `q` / `quit` / `exit`: 退出录制，保存测试脚本
- `u` / `undo`: 撤销上一步操作
- `v-on`: 开启视觉模式
- `v-off`: 关闭视觉模式

## 📁 项目结构说明

```
ui_agent/
├── agent_cli.py             # 🤖 (Agentic) 供超级 Agent 调用的自主探索引擎入口
├── main.py                  # 🙋‍♂️ (Interactive) 人机交互式录制引擎入口
├── conftest.py              # Pytest 核心夹具，跨平台调度与视频/截图报告挂载
├── pytest.ini               # Pytest 运行规则配置
├── config/
│   └── config.py            # 全局配置 (API Keys, 超时, 多环境配置)
├── common/
│   ├── ai.py                # AI 交互基础层 (单步解析与缓存)
│   ├── ai_autonomous.py     # 🤖 自主推理大脑 (带自愈、多模态支持、记忆流)
│   ├── executor.py          # 动作物理执行器与 Python 代码生成
│   │                         # ├── ActionHandler (抽象基类)
│   │                         # ├── ClickHandler
│   │                         # ├── LongClickHandler / HoverHandler
│   │                         # ├── InputHandler
│   │                         # ├── SwipeHandler / PressHandler
│   │                         # ├── AssertExistHandler
│   │                         # └── AssertTextEqualsHandler
│   ├── history_manager.py   # 历史记录管理器与代码回滚流控制
│   ├── logs.py              # 日志系统 (基于 loguru)
│   ├── run_reporter.py      # 结构化运行产物输出 (summary / steps / artifacts)
│   ├── cache/               # 本地混合语义缓存系统 (精准匹配+向量检索)
│   │   ├── cache_manager.py      # 缓存管理器 (L1/L2 混合检索)
│   │   ├── embedding_loader.py   # 句子向量模型加载器 (懒加载、缓存清理)
│   │   ├── cache_hash.py         # UI 页面指纹与指令哈希计算
│   │   ├── cache_storage.py     # 缓存文件的读写与 TTL 管理
│   │   └── cache_stats.py        # 缓存命中率统计
│   └── adapters/            # 📱 跨平台多端底层适配器 (Android/iOS/Web)
│       ├── base_adapter.py      # 适配器基类
│       ├── android_adapter.py   # Android uiautomator2 适配层
│       ├── ios_adapter.py       # iOS facebook-wda 适配层
│       └── web_adapter.py       # Web Playwright 适配层
├── docs/
│   ├── AGENT_GUIDE.md       # 超级 Agent 协作规范 (喂给 Claude/Cursor)
│   ├── capability-matrix.md # 平台/动作/定位器支持矩阵
│   └── skills/              # Agent Tool 描述文件 (如 execute_ui_automation.md)
├── utils/
│   └── utils_xml.py         # Android XML 清洗与降维算法，极致省 Token
└── test_cases/              # 自动生成的自动化测试脚本存放目录
    ├── android/             # Android 平台测试脚本
    ├── ios/                 # iOS 平台测试脚本
    └── web/                 # Web 平台测试脚本
```

## 📊 模块调用链

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py / agent_cli.py                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
   ┌─────────┐           ┌───────────┐           ┌─────────────────┐
   │ AIBrain │           │ UIExecutor│           │StepHistoryManager│
   └────┬────┘           └─────┬─────┘           └────────┬────────┘
        │                      │                          │
        ▼                      ▼                          │
   ┌──────────┐          ┌──────────┐                    │
   │CacheManager│         │ActionHandler│                   │
   └────┬─────┘          └──────────┘                    │
        │                      │                          │
        ▼                      │                          │
   ┌──────────────┐            │                          │
   │EmbeddingModel│            │                          │
   │    Loader    │            │                          │
   └──────────────┘            │                          │
                                │                          │
┌───────────────────────────────┴───────────────────────────────┐
│                    BasePlatformAdapter                         │
│            (AndroidU2Adapter / IosWdaAdapter / WebAdapter)    │
└────────────────────────────────────────────────────────────────┘
```

## 🗂️ 缓存系统架构

项目实现了 **L1/L2 混合语义缓存**，大幅降低大模型 API 调用次数：

### L1 缓存：页面动作缓存
- **适用场景**：在相同骨架的页面，发出了意思极为相近的指令（如点击）
- **匹配方式**：UI 页面指纹哈希 + 指令语义哈希精确匹配
- **命中条件**：UI 树结构相似度 90%+ 且指令完全一致

### L2 缓存：纯问答缓存
- **适用场景**：不管在什么页面，只要问过类似的问题（断言/生成代码），直接取答案
- **匹配方式**：指令语义哈希精确匹配
- **命中条件**：指令完全一致（无视页面）

### 向量语义检索（兜底机制）
当精确匹配未命中时，系统会使用 **Sentence-Transformer** 模型计算指令的语义向量，在缓存中寻找最相似的结果。当相似度达到阈值（L1: 90%, L2: 88%）时，也会命中缓存。

## 📝 更新日志

### 2026-03-30

#### 🏗️ 代码重构
- **EmbeddingModelLoader 职责分离**：将 CacheManager 中的模型加载逻辑抽取到独立的 `EmbeddingModelLoader` 类，提升代码可维护性和可测试性。
  - 原 85 行 `_get_model` 方法简化为 3 行委托调用
  - 模型加载、缓存清理、网络配置等职责清晰分离
  - 支持依赖注入，便于单元测试

#### 🐛 Bug 修复
- **agent_cli.py 平台目录检查**：修复动态路径生成时平台目录可能不存在的 bug，现在会自动创建 `test_cases/<platform>/` 目录。
- **main.py 异常处理改进**：finally 块中的异常处理从空 `pass` 改为记录异常日志 (`log.warning`)，避免异常被静默吞掉。

### 历史版本

- **v0.2.0**: 添加 L1/L2 混合语义缓存系统
- **v0.1.0**: 初始版本，支持 Agentic 和 Interactive 双模式

## ❓ 常见问题 (FAQ)

**Q1: 运行时报错 DeviceNotFoundError 或连接设备失败怎么办？**
确保手机已连上 USB 调试。可以使用 `adb devices` 命令查看是否有设备在线。如果有设备，请再次执行 `python -m uiautomator2 init`。

**Q2: 大模型频繁返回乱码或无法解析动作？**
检查 `config.py` 中的 `MODEL_NAME`。UI 结构理解需要较强的逻辑推理能力，推荐使用千亿参数级别的旗舰模型。如果是国内大模型，建议使用具有强大代码/JSON 输出能力的模型。

**Q3: 录制时点击了，但脚本回放时找不到元素报错？**
可能是由于页面动画或网络加载延迟导致。可以在 `config.py` 中适当增大 `DEFAULT_TIMEOUT`（默认 5.0 秒）以增加容错率。

**Q4: `--vision` 参数什么时候需要开启？**
如果你的测试页面是标准的 Android Native 页面，通常仅靠 XML 压缩算法（默认）就足够了，速度快且便宜。但如果你在测试复杂的 Web H5 画布、Unity 游戏界面，或是遇到了动态乱码 `resource-id`，强烈建议追加 `--vision` 参数，让多模态大模型结合截图精准定位。

**Q5: 为什么 `agent_cli.py` 跑着跑着报错退出了？**
这是触发了**自愈熔断机制**。如果引擎在一个页面连续多次尝试执行动作失败（例如被遮挡），或是 UI 发生"僵死"（点完页面毫无反应），在达到 `--max_retries` 阈值后，它会主动带着非 0 状态码中止，防止大模型陷入无限死循环。此时请查看输出日志修改你的 `--goal` 或补充前置上下文。

**Q6: 视频录制功能无法使用？**
确保已安装 scrcpy。运行 `scrcpy --version` 验证安装。如果仍然失败，检查手机是否授权了屏幕录制权限。失败用例的视频会自动挂载到 Allure 报告中。

**Q7: 语义缓存没有命中，即使我执行了相同的操作？**
请检查：
1. 缓存是否启用：在 `config.py` 中设置 `CACHE_ENABLED = True`
2. UI 树是否有变化：L1 缓存依赖 UI 页面指纹，页面结构大幅变化会导致缓存失效
3. 指令是否完全一致：L2 缓存要求指令文本完全匹配

**Q8: 第一次运行很慢，提示正在下载模型？**
这是正常现象。首次运行时需要下载 Sentence-Transformer 模型（约 100MB），通过国内镜像源加速通常需要 1-3 分钟。后续运行会使用本地缓存，加载速度会大幅提升。

**Q9: 如何清除缓存？**
```python
from common.cache import CacheManager
cm = CacheManager()
cm.clear()  # 清除所有缓存条目
```

## 🐛 问题报告指南

如遇问题，请按以下格式提交反馈：

1. **复现步骤**：清晰的操作步骤或触发命令
2. **错误日志**：完整的错误信息（包括堆栈跟踪）
3. **环境信息**：操作系统、Python 版本、手机型号/系统版本
4. **截图/录像**：如果涉及 UI 问题，提供相关截图或录像

**提交方式**

- 邮件: 592909057@qq.com

感谢你的反馈，我会尽快处理！
