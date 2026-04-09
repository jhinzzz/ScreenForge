# ScreenForge Capability Matrix

本文档描述当前仓库中已经落地并验证过的能力边界，用于替代 README 中的模糊承诺。若上层 Agent 需要机器可读版本，请直接执行 `./.venv/bin/python agent_cli.py --capabilities`；若需要机器可读执行入口，可使用 `--tool-request`、`--tool-stdin` 或 `--mcp-server`。当前三类机器入口已统一支持 `capabilities`、`execute` 和 `load_run` 语义。

## 平台支持总览

| 平台 | 连接能力 | 页面结构采集 | 截图 | 物理动作执行 | 视频/状态产物 | 当前成熟度 |
|---|---|---|---|---|---|---|
| Android | `uiautomator2` | XML 压缩 | 支持 | 支持 | `scrcpy` 录像 | 高 |
| iOS | `facebook-wda` | 暂未实现结构压缩 | 支持 | 基础支持 | 暂无原生录像 | 低 |
| Web | Playwright + CDP | DOM 压缩 | 支持 | 支持 | Playwright 视频 + storage state | 中 |

## CLI 模式支持

| 模式 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| `run` | 支持 | 基础支持 | 支持 | 默认自主探索并生成 pytest 脚本 |
| `doctor` | 支持 | 支持 | 支持 | 只检查环境与前置条件 |
| `plan-only` | 支持 | 基础支持 | 支持 | 连接平台并生成执行前计划，不执行物理动作 |
| `dry-run` | 支持 | 基础支持 | 支持 | 走决策链并输出 would-execute 结果，不执行物理动作 |
| `resume-run-id` | 支持 | 支持 | 支持 | 从已有 run report 恢复最小上下文 |
| `mcp-server` | 支持 | 支持 | 支持 | 以 stdio 方式暴露最小 MCP tools 接口 |

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

## 当前已知边界

1. `APP_ENV_CONFIG` 当前仓库默认只配置了 `dev` 环境，其他环境需用户自行补充。
2. iOS 目前只具备基础接入能力，尚未实现和 Android / Web 同等级的结构采集、录像和启动流程。
3. Web 当前依赖已启动的 Chrome CDP 会话，使用前需要准备好 `WEB_CDP_URL`。
4. `plan-only` 和 `dry-run` 是一阶段控制面能力，重点是预览与排障，不替代正式 `run` 模式。
5. `mcp-server` 当前暴露 `ui_agent_capabilities`、`ui_agent_execute` 和 `ui_agent_load_run` 三个 tools；`--tool-request` / `--tool-stdin` 也已对齐支持 `capabilities`、`execute`、`load_run` 三类 operation。
6. `ui_agent_execute` 会返回统一的 `run_assets` 聚合块，`load_run` 用于按 `run_id` 回读历史运行。
