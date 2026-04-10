# 🤖 ScreenForge (多端/多模态/智能体 UI 自动化引擎)

**中文** | [English](./README_EN.md)

> Agentic UI Automation Framework
>
> Cross-platform agentic UI automation engine for UI exploration, self-healing, and test generation.

ScreenForge 是一个跨平台 UI 自动化引擎，聚焦 UI 探索、交互录制、结构化执行与测试脚本生成。

### 你是谁？从这里开始

| 你是... | 入口 | 第一条命令 |
|---------|------|-----------|
| **人类开发者**，想边看边调试 | `main.py` | `python main.py --platform android` |
| **AI Agent**（Claude Code / Cursor / Codex），想驱动 UI | `agent_cli.py --action` / `--tool-stdin` | 见下方 Agent 快速开始 |

**人类路径**保留自然语言 + 第三方 LLM/VLM 的交互式录制体验。
**Agent 路径**由上层 Agent 负责理解 PRD/命令，ScreenForge 只做结构化执行：`inspect_ui -> action/workflow -> verify`。

## ✨ 核心特性

🗣️ **双入口驱动**：

- **人类交互模式 (`main.py`)**：像聊天一样控制手机，每一步生成标准代码，保留自然语言 + 第三方 LLM/VLM 体验。
- **Agent 执行模式 (`agent_cli.py --action/--workflow`)**：由外部 Agent 先理解 PRD/命令，再调用 ScreenForge 的结构化能力完成抓树、定位、执行、生成脚本与资产沉淀。`agent_cli.py` 是 6 行 shim，真实逻辑在 `cli/` 包内。

🎯 **ref 定位系统**：`inspect_ui` 为每个可交互元素分配 ref 编号（@1, @2...），附带 bbox 坐标（x, y, w, h）。上层 Agent 可直接引用 ref 定位，无需猜测 resource-id 或 xpath。

👁️ **多模态视觉感知 (`--vision`)**：除了 XML 降维清洗算法，还支持实时截图标注（ref 编号叠加到截图上）和视觉 fallback（VLM）。当 DOM/XML 无法定位目标时（Canvas、游戏、自绘 UI），引擎自动调用 VLM 从截图解析坐标。

🛡️ **结构化自愈引擎**：`HealResult` 返回 `confidence / fix_description / fixed_code`，经 `ast.parse` 语法校验、置信度阈值过滤（默认 0.7），覆盖前自动 `.bak` 备份。内置 UI 僵死检测和熔断机制，杜绝 Token 浪费。

📦 **跨平台大一统**：底层采用优雅的 Adapter 模式，一键切换操作目标：

- `Android` (uiautomator2)
- `iOS` (facebook-wda)
- `Web` (Playwright)

🎬 **全链路追踪与回放**：自动生成带有 `@allure.step` 的规范代码，支持断言自动失败截图，以及基于 Scrcpy/原生方案的**自动执行视频录制与报告挂载**。

⚡ **极致 Token 优化**：内置 Android XML 清洗降维算法，剔除底层系统噪音、独立符号和巨型冗余节点，Token 消耗降低 80% 以上，响应更快、成本更低。

🧾 **结构化运行产物 (`--json`)**：`agent_cli.py` 支持向 stdout 输出 JSON Lines 事件流，并在 `report/runs/<run_id>/` 下生成 `summary.json`、`steps.jsonl`、`artifacts.json` 和视觉截图索引，便于上层 Agent 或编排系统消费。

🧩 **半结构化 Workflow DSL (`--workflow`)**：CLI 支持从 YAML workflow 读取确定性步骤，并通过 `--workflow-var KEY=VALUE` 覆盖变量模板，以 `plan-only / dry-run / run` 三种模式接入现有执行与报告链路，适合沉淀高频、稳定业务流。对 Agent 集成，推荐优先使用这一路径，而不是把自然语言直接交给 `--goal`。

🎛️ **即时动作层 (`--action`)**：CLI 支持直接执行或预演单个 `click / input / assert_exist / ...` 动作，适合排障、快速验证和上层 Agent 的可控单步调用。

🧭 **能力快照 (`--capabilities`)**：CLI 可直接输出当前代码已落地的模式、控制面、动作与平台快照，供上层 Agent 或集成层在执行前做能力探测，减少文档漂移。

🧰 **工具协议入口 (`--tool-request` / `--tool-stdin`)**：CLI 支持从单个 JSON 请求文件或 stdin 读取机器可读请求，并返回统一 JSON 响应。当前已与 MCP 对齐，统一支持 `capabilities`、`inspect_ui`、`load_case_memory`、`execute`、`load_run` 五类操作，便于外部 Agent 直接消费。

🧠 **跨运行测试记忆 (`memory/case_memory.json`)**：真正执行 `run` 后，ScreenForge 会把成功动作、定位经验、pytest 资产与失败恢复建议增量沉淀到 `case_memory.json`，供后续 Agent 运行持续复用。

🔌 **最小 ScreenForge MCP Server (`--mcp-server`)**：CLI 现在可直接以 stdio 方式暴露最小 MCP server，支持 `initialize / tools/list / tools/call / ping`，并通过 `ui_agent_capabilities`、`ui_agent_inspect_ui`、`ui_agent_load_case_memory`、`ui_agent_execute` 与 `ui_agent_load_run` 五个 tools 复用现有执行链与运行资产。

## 🛠️ 环境依赖与安装

### 1. 基础要求

- Python 3.10 或以上版本（推荐使用 Python 3.11+）
- 一台 Android 手机（或模拟器），已开启开发者模式和 USB 调试，并通过数据线连接到电脑

### 2. 创建虚拟环境（推荐）

强烈推荐使用虚拟环境隔离项目依赖：

```bash
# 创建虚拟环境
python -m venv .venv

# 推荐直接使用虚拟环境内的 Python，避免 shell 中存在多套解释器时发生漂移
./.venv/bin/python --version
```

### 3. 安装 Python 依赖库

激活虚拟环境后，在项目根目录下执行：

```bash
./.venv/bin/python -m pip install -r requirement.txt
```

如果你只想手动安装核心依赖，可以执行以下命令：

```bash
pip install uiautomator2 openai pytest allure-pytest loguru filelock numpy sentence-transformers
```

*(注: `requirement.txt` 已包含 Web 所需的 `playwright` 依赖；若需支持 iOS，请额外安装 `facebook-wda`)*

### 4. 初始化 Android 设备

运行以下命令，向手机端推送 uiautomator2 的守护进程（ATX 应用）：

```bash
./.venv/bin/python -m uiautomator2 init
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

**多环境配置**：当前仓库默认仅配置 `dev` 环境；如需 `prod` / `us_dev` / `us_prod`，请先在 `config/config.py` 中补充 `APP_ENV_CONFIG`。

## 🚀 核心工作流一：人类交互调试 (`main.py`)

如果你是人类操作者，并希望直接通过自然语言边看边调试，请使用：

```bash
./.venv/bin/python main.py --platform android
./.venv/bin/python main.py --platform web
```

这条路径会保留当前项目原有的自然语言 + 第三方 LLM/VLM 交互体验。

## 🚀 核心工作流二：接入超级 Agent (Agentic Mode)

将 ScreenForge 作为底层 Tool/Skill 赋能给 Claude Code、Cursor 等外部 Agent。让 Agent 阅读 `docs/agent_guide.md` 学习集成规范。

**Agent 快速开始**（3 步）：

```bash
# 1. 获取当前页面 UI 树（Agent 自己分析，不是让 ScreenForge 做自然语言理解）
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin

# 2. Agent 分析 UI 树后，下发单步动作
python agent_cli.py --action click --platform web --locator-type text --locator-value "Login"

# 3. 再次 inspect_ui 确认页面变化，循环直到完成
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin
```

**批量执行**用 workflow：

```bash
python agent_cli.py --workflow ./docs/workflows/login_failure.yaml \
                    --output "test_cases/test_login.py" \
                    --platform android --json
```

**MCP 集成**：

```bash
python agent_cli.py --mcp-server
```

### 新增入口模式

```bash
# 环境体检
./.venv/bin/python agent_cli.py --doctor --platform android

# 只生成执行计划，不做物理动作
./.venv/bin/python agent_cli.py --workflow ./docs/workflows/login_failure.yaml --plan-only --platform android

# 只模拟执行链，不做物理动作
./.venv/bin/python agent_cli.py --workflow ./docs/workflows/login_failure.yaml --dry-run --platform android

# 基于上一次 run 恢复最小上下文
./.venv/bin/python agent_cli.py --workflow ./docs/workflows/login_failure.yaml --resume-run-id <run_id> --platform android

# 使用 workflow DSL 做半结构化预览 / 执行
./.venv/bin/python agent_cli.py --workflow ./docs/workflows/login_failure.yaml --plan-only --platform android
./.venv/bin/python agent_cli.py --workflow ./docs/workflows/login_failure.yaml --dry-run --platform android --workflow-var submit_label=立即登录 --json
./.venv/bin/python agent_cli.py --workflow ./docs/workflows/login_failure.yaml --platform android --workflow-var username=qa_user

# 使用即时动作层做单步预演 / 执行
./.venv/bin/python agent_cli.py --action click --action-name "点击登录按钮" --locator-type text --locator-value 登录 --platform android --dry-run
./.venv/bin/python agent_cli.py --action input --action-name "输入用户名" --locator-type text --locator-value 用户名 --extra-value qa_user --platform android

# 输出当前 CLI 已落地能力快照
./.venv/bin/python agent_cli.py --capabilities

# 通过机器可读请求调用 CLI
./.venv/bin/python agent_cli.py --tool-request ./docs/tool_request_examples/inspect_ui.json
./.venv/bin/python agent_cli.py --tool-request ./docs/tool_request_examples/load_case_memory.json
./.venv/bin/python agent_cli.py --tool-request ./docs/tool_request_examples/workflow_plan.json
./.venv/bin/python agent_cli.py --tool-request ./docs/tool_request_examples/load_run.json
cat ./docs/tool_request_examples/workflow_plan.json | ./.venv/bin/python agent_cli.py --tool-stdin

# 以 stdio 方式启动最小 ScreenForge MCP server
./.venv/bin/python agent_cli.py --mcp-server
```

如果 `doctor` 报告 `venv_consistency` 问题，可执行：

```bash
./.venv/bin/python scripts/repair_venv.py
```

当前 `doctor` 会额外检查：

- Android: `adb` 是否存在、`adb devices` 是否能看到可用设备
- Web: `WEB_CDP_URL` 端口是否可达、`/json/version` 是否返回有效的 CDP 元数据
- Worktree 场景下的 `.venv` 是否发生 shebang / `pyvenv.cfg` 漂移

若你是在受限 Agent/沙箱里运行 `doctor`，并看到“当前运行环境限制了 adb daemon 的本地端口监听”或“当前运行环境限制了本地 TCP 连接检查”，这通常表示本地权限受限导致的假阴性，而不一定是设备或 Chrome 本身故障。此时应优先在宿主终端直接执行 `adb devices` 或 `curl -sS http://localhost:9222/json/version` 复核。

### Pytest 运行约定

默认执行 `./.venv/bin/python -m pytest` 时，`test_cases/android/`、`test_cases/ios/`、`test_cases/web/` 下的真实平台回放脚本会被自动跳过，以保证离线回归在无设备或受限环境下也能稳定完成。

如需显式运行真实平台回放测试，请开启 `RUN_LIVE_PLATFORM_TESTS`，并通过 `TEST_PLATFORM` 指定目标平台：

```bash
# 仅运行 Android 真机回放测试
RUN_LIVE_PLATFORM_TESTS=true TEST_PLATFORM=android ./.venv/bin/python -m pytest test_cases/android

# 仅运行 Web 真浏览器回放测试
RUN_LIVE_PLATFORM_TESTS=true TEST_PLATFORM=web ./.venv/bin/python -m pytest test_cases/web
```

### CLI 核心参数说明

- `-goal`: (兼容入口) 宏观测试目标，会调用内部 LLM 自主探索。仅用于人工命令行实验，**Agent 集成禁止使用**。
- `-output`: (可选) 脚本输出的绝对或相对路径。引擎会自动创建平台目录（如 `test_cases/android/`）。
- `-platform`: (可选) 目标平台 (`android` | `ios` | `web`)。
- `-vision`: (可选 Flag) 开启多模态视觉辅助（建议在遇到复杂图形时开启）。
- `-json`: (可选 Flag) 向 stdout 输出 JSON Lines 事件流，供上层 Agent / 编排系统解析。
- `-context`: (可选) 传入包含 PRD、帐号密码等复杂规则的临时 txt/md 文件路径。
- `-max_retries`: (可选) 熔断阈值：单步操作的最大连续容错重试次数，默认 3。
- `-doctor`: (可选 Flag) 只做配置、依赖与平台前置条件体检。
- `-plan-only`: (可选 Flag) 基于当前页面生成执行计划，不执行物理动作，也不生成正式脚本。
- `-dry-run`: (可选 Flag) 走决策链并输出 would-execute 结果，不执行物理动作，也不生成正式脚本。
- `-resume-run-id`: (可选) 从 `report/runs/<run_id>/` 中恢复最小上下文，便于继续分析或重试。
- `-workflow`: (可选) 指定 YAML 工作流文件，启用半结构化执行模式；与 `--goal` 互斥。
- `-workflow-var`: (可选，可重复) 覆盖 workflow 中的模板变量，格式为 `KEY=VALUE`。
- `-action`: (可选) 指定单步即时动作；与 `--goal`、`--workflow` 互斥。
- `-action-name`: (可选) 指定单步即时动作的人类可读名称。
- `-locator-type`: (按需) 即时动作使用的定位器类型；`swipe` / `press` 等全局动作可省略。
- `-locator-value`: (按需) 即时动作使用的定位器值；`swipe` / `press` 等全局动作可省略。
- `-extra-value`: (按需) 单步动作附加值，如输入内容、按键名或断言期望文本。
- `-capabilities`: (可选 Flag) 输出当前 CLI 已落地能力的机器可读快照，不启动执行链。
- `-tool-request`: (可选) 从 JSON 文件读取机器可读请求，并返回统一 JSON 响应；支持 `capabilities`、`execute`、`load_run`。
- `-tool-stdin`: (可选 Flag) 从 stdin 读取机器可读请求，并返回统一 JSON 响应；支持 `capabilities`、`execute`、`load_run`。
- `-mcp-server`: (可选 Flag) 以 stdio 模式启动最小 ScreenForge MCP server，不进入普通 CLI 执行链。

默认 `run` 模式在探测完成后，若成功会以 `Exit Code 0` 退出，失败或熔断则以 `Exit Code 1` 退出；`doctor`、`plan-only`、`dry-run` 也会将结果写入 `report/runs/<run_id>/`，便于上层 Agent 接续消费。若提供 `--workflow`，则 `plan-only / dry-run / run` 会直接复用工作流步骤；若同时提供 `--workflow-var`，则会先完成变量替换再进入执行链。若提供 `--action`，则会复用同一套 report / dry-run / codegen 链路完成单步执行。`tool / MCP` 路径下，推荐先用 `inspect_ui` 与 `load_case_memory` 完成分析，再执行 `workflow/action`。

### 运行产物

- `report/runs/<run_id>/summary.json`: 本次运行的状态摘要、退出码、输出脚本路径
- `report/runs/<run_id>/steps.jsonl`: 结构化事件流落盘副本
- `report/runs/<run_id>/artifacts.json`: 已生成脚本、截图等产物索引
- `report/runs/<run_id>/pytest_replay.json`: 面向回放和恢复的 pytest 资产清单
- `report/runs/<run_id>/screenshots/`: `--vision` 模式下的运行截图
- `memory/case_memory.json`: 跨运行测试记忆，保存成功动作、定位经验、pytest 资产与恢复建议

其中 `summary.json` 在一阶段控制面下额外包含：

- `execution_mode`: `run` / `doctor` / `plan_only` / `dry_run`
- `resume_from_run_id`: 若本次基于历史 run 恢复，则记录来源 run_id
- `resume_context_available`: 是否成功恢复最小上下文
- `plan_preview`: `plan-only` 模式下的执行计划摘要
- `dry_run_preview`: `dry-run` 模式下的 would-execute 结果摘要
- `failure_analysis`: 失败分类、恢复建议和推荐命令；成功态为空
- `pytest_asset`: pytest 回放入口、manifest 路径和 resume 命令集合
- `workflow_summary`: workflow 名称、路径、步数，以及预览或执行结果摘要
- `action_summary`: 即时动作名称、定位参数，以及预览或执行结果摘要
- `control_summary`: 统一控制面摘要。无论当前是 `goal`、`workflow`、`action` 还是 `doctor`，都可优先读取这里的 `control_kind`、`control_label`、`source_ref` 和关键执行信息

`--tool-request` 与 `--tool-stdin` 现在都支持 `capabilities`、`inspect_ui`、`load_case_memory`、`execute`、`load_run`。其中：

- `inspect_ui`：连接目标平台并返回清洗后的 XML/DOM 树，供外部 Agent 自主分析。
- `load_case_memory`：读取跨运行测试记忆，复用已有成功动作、定位经验和 pytest 资产。
- `execute`：直接内联 `summary.json` 内容，并返回 `run_dir`、`summary_path`、`run_assets`、`case_memory_hit` 与统一 `exit_code`。
- `load_run`：按 `run_id` 直接回读历史运行。

`--mcp-server` 会把同样的结构化 payload 封装到 MCP `tools/call` 的 `structuredContent` 中，便于外部 Agent 原生读取；若外部 Agent 需要按 `run_id` 回读历史运行，可直接调用 `ui_agent_load_run`。

### 迁移者建议先看

- `docs/agent_guide.md`: 给上层 Agent 的集成规范（首日关键路径）
- `docs/capability-matrix.md`: 平台/动作/定位器支持矩阵
- `.claude/skills/`: Claude Code 原生 Skill 定义（operate-web / operate-android / run-workflow / diagnose）

## 💻 核心工作流二：人机交互录制 (Interactive Mode)

如果您希望手动、一步一步地把控录制细节，可以启动原汁原味的交互式引擎：

```bash
./.venv/bin/python main.py
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
screenforge/
├── agent_cli.py             # 兼容入口 (6 行 shim，委托给 cli/dispatch.py)
├── main.py                  # 🙋‍♂️ (Interactive) 人机交互式录制引擎入口
├── conftest.py              # Pytest 核心夹具，跨平台调度与视频/截图报告挂载
├── pytest.ini               # Pytest 运行规则配置
├── cli/                     # 🤖 CLI 真实分发层（P1-2 拆分自 agent_cli.py）
│   ├── dispatch.py          # CLI 入口 main()，参数解析后按模式分发
│   ├── parser.py            # build_parser, validate_cli_args
│   ├── shared.py            # 懒加载代理、适配器连接、UI 状态抓取
│   ├── reporter.py          # 报告辅助函数
│   ├── doctor.py            # 环境体检
│   ├── tool_protocol_handlers.py  # --tool-stdin / --tool-request / --mcp-server
│   └── modes/               # 各执行模式
│       ├── default.py       # --goal 自主探索循环
│       ├── action.py        # --action 单步执行
│       ├── workflow.py      # --workflow 半结构化执行
│       ├── plan.py          # --plan-only
│       └── dry_run.py       # --dry-run
├── config/
│   └── config.py            # 全局配置 (API Keys, 超时, 多环境配置, 自愈阈值)
├── common/
│   ├── ai.py                # AI 交互基础层 (单步解析与缓存)
│   ├── ai_autonomous.py     # 🤖 自主推理大脑 (带自愈、多模态支持、记忆流)
│   ├── ai_heal.py           # 结构化自愈引擎 (HealResult, 4 策略 JSON 解析, AST 校验)
│   ├── executor.py          # 动作物理执行器与 Python 代码生成
│   ├── visual_fallback.py   # 视觉 fallback (VLM 坐标解析)
│   ├── history_manager.py   # 历史记录管理器与代码回滚流控制
│   ├── logs.py              # 日志系统 (基于 loguru)
│   ├── run_reporter.py      # 结构化运行产物输出 (summary / steps / artifacts)
│   ├── cache/               # 本地混合语义缓存系统 (精准匹配+向量检索)
│   └── adapters/            # 📱 跨平台多端底层适配器 (Android/iOS/Web)
├── utils/
│   ├── utils_xml.py         # Android XML 清洗与降维算法
│   ├── utils_web.py         # Web DOM 压缩与 URL 处理
│   └── screenshot_annotator.py  # 截图标注 (ref 编号叠加到截图上)
├── tests/                   # 框架单元测试 (32 用例)
│   ├── test_ai_heal.py      # 自愈引擎解析与置信度
│   ├── test_executor.py     # ref 缓存、定位器构建、动作处理器
│   ├── test_screenshot_annotator.py  # 截图标注
│   ├── test_utils_web.py    # DOM 压缩与 URL 归一化
│   └── test_visual_fallback.py      # VLM 坐标解析
├── docs/
│   ├── agent_guide.md       # Agent 集成规范
│   └── capability-matrix.md # 平台/动作/定位器支持矩阵
└── test_cases/              # 自动生成的自动化测试脚本存放目录
    ├── android/
    ├── ios/
    └── web/
```

## 📊 模块调用链

```
┌────────────────────────────────────────────────────────────────────┐
│  main.py (人类)    agent_cli.py → cli/dispatch.py (Agent)         │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    ┌──────────┐        ┌───────────┐        ┌─────────────────┐
    │ AIBrain  │        │ UIExecutor│        │StepHistoryManager│
    └────┬─────┘        └─────┬─────┘        └────────┬────────┘
         │                    │                       │
    ┌────▼─────┐         ┌────▼──────┐                │
    │CacheManager│        │ActionHandler│               │
    └──────────┘         └───────────┘                │
                               │                       │
┌──────────────────────────────┴───────────────────────────────┐
│                    BasePlatformAdapter                        │
│            (AndroidU2Adapter / IosWdaAdapter / WebAdapter)   │
└──────────────────────────────────────────────────────────────┘
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
这是触发了**自愈熔断机制**。如果引擎在一个页面连续多次尝试执行动作失败（例如被遮挡），或是 UI 发生"僵死"（点完页面毫无反应），在达到 `--max_retries` 阈值后，它会主动带着非 0 状态码中止，防止执行链陷入无限死循环。此时请查看输出日志，修改你的 workflow/action 设计或补充前置上下文。

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

- 邮件: jhin.fangz@gmail.com

感谢你的反馈，我会尽快处理！
