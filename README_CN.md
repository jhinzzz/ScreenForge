# ScreenForge

[![CI](https://github.com/jhinzzz/ScreenForge/actions/workflows/ci.yml/badge.svg)](https://github.com/jhinzzz/ScreenForge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**中文** | [English](./README.md)

> **让你的 AI agent 跑测试，你留下那个 pytest 文件。**
>
> 用自然语言描述流程，看着 agent 在真实站点上点击，最后带走一个会自愈、能进 CI、UI 改版也不挂的 pytest 脚本。_（还能驱动真机 iOS + Android，不只是 Chrome。）_

ScreenForge 是一个 AI 驱动的 UI 自动化引擎，将自然语言转化为可执行的测试脚本。与录制回放工具不同，你不需要自己操作——AI 替你完成。

## 为什么选 ScreenForge？

| | Playwright Codegen | Browser Use | Midscene.js | **ScreenForge** |
|---|---|---|---|---|
| 需要自己操作？ | 是 | 否 | 否 | **否** |
| 生成可回放的测试脚本？ | 是 | 否 | 否 | **是 (pytest)** |
| UI 变更时自愈？ | 否 | 否 | 否 | **是** |
| 可作为 AI Agent 工具 (MCP)？ | 否 | 是 | 否 | **是** |
| 能驱动真机 iOS / Android？ | 否 | 否 | 否 | **是** |

**核心架构**：你的 AI Agent 是大脑（理解需求、做决策），ScreenForge 是手脚（执行 UI 动作、生成代码）。

## 快速开始

```bash
pip install screenforge

# 零配置体验，无需 API Key：
screenforge --demo

# 正式使用，设置 LLM Key：
export OPENAI_API_KEY=sk-...

# 获取当前页面 DOM 树（供 Agent 分析）：
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin

# 执行单步动作：
screenforge --action click --platform web --locator-type text --locator-value "Login"
```

### 简写模式

```bash
# 等价于 --action click --locator-type text --locator-value "Login" --platform web
screenforge click "Login"

# CSS 选择器
screenforge click "#email"

# ref 定位
screenforge click "@3"

# 输入
screenforge input "#email" "admin@example.com"

# 导航
screenforge goto "https://example.com"

# 查看 UI 树
screenforge inspect
```

## 工作流程

```
你 (或你的 AI Agent)            ScreenForge
        |                            |
        |---- "测试登录流程" -------->|
        |                            |-- inspect_ui (获取 DOM 树)
        |<-- DOM 树 ----------------|
        |                            |
        |---- click #email -------->|
        |---- input "user@..." ---->|
        |---- click "登录" -------->|
        |                            |
        |<-- pytest 脚本 -----------|
        |<-- Allure 报告 -----------|
```

每一步：**抓取 -> 决策 -> 执行 -> 验证**。AI 做决策，ScreenForge 负责执行。

## 核心特性

- **留下真实的 pytest 文件**：每次运行都产出可回放的 `pytest` 脚本（含 Allure 注解），可直接进 CI —— 不是一次性的黑盒 agent 运行。
- **自愈引擎**：UI 改版、定位器失效时，引擎用置信度评分 + AST 校验自动修复，让你提交进仓库的测试存活下来。
- **由 agent 来点击**：你（或你的 AI agent）描述意图，ScreenForge 负责读 DOM、执行、校验 —— 你永远不用手工录制。
- **真机，而不只是浏览器**：通过同一套协议驱动 Android(uiautomator2) 和 iOS(wda) 真机 —— 这是纯 Web agent（Playwright MCP、Browser Use）做不到的唯一一件事。
- **L1/L2 语义缓存**：相同页面 + 相同指令 = 即时响应，无需 LLM 调用
- **视觉 fallback**：DOM 无法定位时（Canvas、游戏），VLM 从截图解析坐标
- **MCP Server**：任何 MCP 兼容的 Agent 可原生驱动 ScreenForge
- **结构化输出**：JSON Lines 事件流 + `report/runs/<id>/` 产物，便于 CI 集成
- **实时镜像台（Live Mirror）**：一边跑用例，一边在浏览器里看生成的 pytest 代码逐行长出 + 实时截图 —— `screenforge --playground`。见 [实时镜像台指南](docs/playground-guide_CN.md)

## Agent 集成 (Claude Code / Cursor / Codex)

ScreenForge 作为 AI Agent 的工具暴露。标准循环：

```bash
# 1. 获取页面结构（Agent 自己分析）
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin

# 2. Agent 决策后下发精确动作
screenforge --action click --platform web --locator-type text --locator-value "Login"

# 3. 验证结果，循环
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin
```

批量操作用 workflow：

```bash
screenforge --workflow ./workflows/login.yaml --platform web --json
```

启动 MCP Server：

```bash
screenforge --mcp-server
```

详见 [Agent 集成指南](docs/agent_guide.md)。

## 安装（从源码）

```bash
git clone https://github.com/jhinzzz/ScreenForge.git
cd ScreenForge
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

按平台安装：
- 仅 Web：`pip install -e .`（默认，含 Playwright）
- Android：`pip install -e ".[android]"`
- iOS：`pip install -e ".[ios]"`
- ML/缓存：`pip install -e ".[ml]"`（sentence-transformers 语义缓存）

## 配置

```bash
# 必填：LLM API Key（OpenAI 兼容端点）
export OPENAI_API_KEY=sk-...

# 可选：自定义端点（默认 api.openai.com）
export OPENAI_BASE_URL=https://api.openai.com/v1

# 可选：模型（默认 gpt-4o）
export MODEL_NAME=gpt-4o
```

或创建 `.env` 文件（从 `.env_template` 复制）。

## 了解更多

| 资源 | 说明 |
|------|------|
| [Agent 集成指南](docs/agent_guide.md) | AI Agent 集成协议 |
| [能力矩阵](docs/capability-matrix_CN.md) | 支持的平台、动作和定位器 |
| [架构深挖](docs/architecture-deep-dive.md) | 大脑/手脚分工、语义缓存、自愈 AST 门禁、工程素养即特性 |
| [示例](docs/examples/) | 真实提交的 workflow + 它生成的绿色 pytest |
| [实时镜像台指南](docs/playground-guide_CN.md) | Live Mirror — 边跑用例边看代码与截图实时增长 |
| [Workflow 示例](docs/workflows/) | YAML workflow 模板 |
| [变更日志](CHANGELOG_CN.md) | 版本历史 |

## 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。欢迎 Issue 和 PR！

## 许可证

[MIT](LICENSE)
