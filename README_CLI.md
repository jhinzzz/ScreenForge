# 📱 ScreenForge - 使用参考手册

欢迎 Super Agent。ScreenForge 是一个提供多端 UI 驱动和代码生成能力的自动化框架。作为外部主控大脑，你可以通过调用本框架提供的 CLI 工具，完成端到端的自动化测试用例编写。

# 🛠️ 你的核心工具 (Skill)

你目前拥有以下本地命令行工具可以调用：

## 1. `agent_cli.py` (自主探索 + 预执行控制器)

这个工具既支持基于 `--goal` 的自主探索，也支持基于 `--workflow` 的半结构化执行，以及基于 `--action` 的单步即时动作。除默认 `run` 模式外，还支持 `--doctor`、`--plan-only`、`--dry-run`、`--resume-run-id`、`--capabilities`、`--tool-request`、`--tool-stdin` 和 `--mcp-server`。若追加 `--json`，它会向 stdout 输出结构化事件流，并在 `report/runs/<run_id>/` 下落盘运行摘要；`doctor` 模式会额外输出可直接消费的 `doctor_summary` 分组诊断事件。对上层 Agent，建议优先读取 `summary.json` 里的 `control_summary`，不用再区分当前是 goal、workflow 还是 action；若只想探测 ScreenForge 已落地能力，可直接调用 `--capabilities`；若想用机器协议执行能力，可调用 `--tool-request`、`--tool-stdin` 或 `--mcp-server`，其中 `--tool-request` / `--tool-stdin` 现已与 MCP 对齐，统一支持 `capabilities`、`execute` 和 `load_run` 三类操作，并优先消费返回里的 `run_assets`。

**调用语法:**

```python
./.venv/bin/python agent_cli.py --goal "<你的测试目标>" --context "<(可选)包含详细约束的文件路径>" --env "<(可选)dev>" --platform "<(可选)android/ios/web>" [--vision] [--json] [--plan-only|--dry-run]
./.venv/bin/python agent_cli.py --workflow "<workflow.yaml>" --env "<(可选)dev>" --platform "<(可选)android/ios/web>" [--workflow-var KEY=VALUE] [--json] [--plan-only|--dry-run]
./.venv/bin/python agent_cli.py --action "<click|input|assert_exist|...>" --locator-type "<(按需)text/resourceId/...>" --locator-value "<(按需)定位值>" [--extra-value VALUE] [--action-name NAME] --platform "<(可选)android/ios/web>" [--json] [--plan-only|--dry-run]
./.venv/bin/python agent_cli.py --capabilities
./.venv/bin/python agent_cli.py --tool-request "<request.json>"
cat "<request.json>" | ./.venv/bin/python agent_cli.py --tool-stdin
./.venv/bin/python agent_cli.py --mcp-server
```

**调用示例:**

```python
./.venv/bin/python agent_cli.py --goal "验证用户使用错误密码登录时，会出现'密码错误'的提示" --context "./docs/login_prd.md" --platform android --json
```

```python
./.venv/bin/python agent_cli.py --doctor --platform android
./.venv/bin/python agent_cli.py --goal "验证用户使用错误密码登录时，会出现'密码错误'的提示" --platform android --plan-only
./.venv/bin/python agent_cli.py --goal "验证用户使用错误密码登录时，会出现'密码错误'的提示" --platform android --dry-run
./.venv/bin/python agent_cli.py --goal "继续验证登录失败提示" --resume-run-id "<run_id>" --platform android
./.venv/bin/python agent_cli.py --workflow "./docs/workflows/login_failure.yaml" --platform android --plan-only
./.venv/bin/python agent_cli.py --workflow "./docs/workflows/login_failure.yaml" --platform android --workflow-var username=qa_user --dry-run --json
./.venv/bin/python agent_cli.py --workflow "./docs/workflows/login_failure.yaml" --platform android --workflow-var username=qa_user --workflow-var submit_label=立即登录
./.venv/bin/python agent_cli.py --action click --action-name "点击登录按钮" --locator-type text --locator-value 登录 --platform android --dry-run
./.venv/bin/python agent_cli.py --action input --action-name "输入用户名" --locator-type text --locator-value 用户名 --extra-value qa_user --platform android
./.venv/bin/python agent_cli.py --capabilities
./.venv/bin/python agent_cli.py --tool-request "./docs/tool_request_examples/workflow_plan.json"
./.venv/bin/python agent_cli.py --tool-request "./docs/tool_request_examples/load_run.json"
cat "./docs/tool_request_examples/workflow_plan.json" | ./.venv/bin/python agent_cli.py --tool-stdin
./.venv/bin/python agent_cli.py --mcp-server
```


# 🧠 你的工作流 (Workflow)

当人类让你“根据 PRD 编写一个登录模块的自动化测试用例”时，请严格遵循以下步骤：

1. 分析与理解: 阅读用户提供的 PRD 或 Git Diff 文件，拆解出需要测试的核心业务流。

2. 生成任务描述: 将业务流转换为一段清晰的、包含前置条件和预期断言的 goal（目标）。

3. 先做体检或预览:
   - 环境不确定时先执行 `./.venv/bin/python agent_cli.py --doctor --platform ...`
   - `doctor` 会检查配置、依赖、`.venv` 一致性，以及 Android 设备连接、iOS WebDriverAgent 状态、Web CDP 调试端点
   - 想先预览路径时执行 `./.venv/bin/python agent_cli.py --goal "..." --plan-only ...`
   - 想看 would-execute 结果时执行 `./.venv/bin/python agent_cli.py --goal "..." --dry-run ...`
   - 如果报告 `venv_consistency`，先执行 `./.venv/bin/python scripts/repair_venv.py`
4. 调用底层引擎:
   - 若你只想探测当前 CLI 已落地能力，先执行 `./.venv/bin/python agent_cli.py --capabilities`
   - 若你需要用单个 JSON 请求与 CLI 对接，执行 `./.venv/bin/python agent_cli.py --tool-request "<request.json>"` 或 `cat "<request.json>" | ./.venv/bin/python agent_cli.py --tool-stdin`
   - `tool-request/tool-stdin` 与 MCP 统一支持 `capabilities`、`execute`、`load_run` 三类 operation；`load_run` 适合按 `run_id` 回读历史运行和回放资产
   - 若你需要让外部 Agent 通过原生工具协议接入，执行 `./.venv/bin/python agent_cli.py --mcp-server`
   - MCP 下可用 `ui_agent_capabilities` 探测能力、`ui_agent_execute` 执行请求、`ui_agent_load_run` 按 `run_id` 回读历史运行和回放资产
   - 自主探索时执行 `./.venv/bin/python agent_cli.py --goal "..."`
   - 半结构化执行时执行 `./.venv/bin/python agent_cli.py --workflow "...yaml"`
   - 若 workflow 定义了变量占位符，可追加一个或多个 `--workflow-var KEY=VALUE`
   - 想执行或预演单个可控动作时，执行 `./.venv/bin/python agent_cli.py --action ...`
   - 若你需要稳定解析执行过程，请追加 `--json`
5. 验证生成结果: 命令执行完毕后，读取输出脚本，并同步检查 `report/runs/<run_id>/summary.json`、`steps.jsonl` 与 `pytest_replay.json`，确认退出码、最终状态、失败分析和 pytest 回放入口是否符合预期。
6. 归档与重命名: 如果你没有显式传入 `--output`，底层引擎会按平台和时间戳自动命名。若代码正常，你可以再使用 shell 命令重命名为更有业务语义的文件名。
7. 运行验收: 执行 `./.venv/bin/python -m pytest test_cases/test_login_failure.py` 验证脚本的可执行性。

补充约定：
- 默认 `./.venv/bin/python -m pytest` 会跳过 `test_cases/android|ios|web/` 下的真实平台回放脚本，避免无设备、无浏览器或受限 Agent 环境导致整套离线回归失败。
- 若你需要真正回放这些脚本，请显式设置 `RUN_LIVE_PLATFORM_TESTS=true`，并配合 `TEST_PLATFORM=android|ios|web` 运行对应目录下的用例。
- 示例：`RUN_LIVE_PLATFORM_TESTS=true TEST_PLATFORM=android ./.venv/bin/python -m pytest test_cases/android`

# 🔧 Doctor 快速修复

`doctor` 模式除了输出 `doctor_summary` 外，还会为常见失败项补充 `fix_command`、`fix_doc` 和 `fix_doc_section`，方便上层 Agent 或研发直接消费。

## 配置

- 若提示 `OPENAI_API_KEY 未配置` 或 `WEB_CDP_URL` 不合法，先检查根目录 `.env` / `.ENV`，再重新执行 `./.venv/bin/python agent_cli.py --doctor --platform ...`
- worktree 会自动向上查找最近祖先目录中的 `.env` 或 `.ENV`

## 运行环境

- 若提示 `venv_consistency`，执行 `./.venv/bin/python scripts/repair_venv.py`
- 若提示 `runtime_paths`，确认 `test_cases/` 与 `report/runs/` 可写

## Android

- 若提示 `uiautomator2` 缺失，执行 `./.venv/bin/python -m pip install -r requirement.txt`
- 若提示 `adb_devices`，先执行 `adb devices`，再确认设备在线、USB 调试已开启且已授权
- 若提示 `adb` 不在 PATH，先安装 Android Platform Tools，再重新打开终端验证
- 若提示“当前运行环境限制了 adb daemon 的本地端口监听”，说明你当前是在受限 Agent/沙箱中运行；请先在宿主终端直接执行 `adb devices`，或放宽本地网络权限后重试

## iOS

- 若提示 `wda` 缺失，执行 `./.venv/bin/python -m pip install facebook-wda`
- 若提示 `http://localhost:8100` 或 `wda_status`，确认 WebDriverAgent 已在真机启动，并且本地 8100 端口映射可访问

## Web

- 若提示 `playwright` 缺失，执行 `./.venv/bin/python -m pip install playwright`
- 若提示 `http://localhost:9222` 或 `cdp_debug_endpoint`，确认 Chrome 以 `--remote-debugging-port=9222` 启动，且 `WEB_CDP_URL` 指向可访问的 CDP 端点
- 若提示“当前运行环境限制了本地 TCP 连接检查”，说明你当前是在受限 Agent/沙箱中运行；请先在宿主终端直接执行 `curl -sS http://localhost:9222/json/version`，或放宽本地网络权限后重试

# ⚠️ 注意事项与约束

- 千万不要手动修改生成的 test_cases/*.py 中的 UI 定位器（如 d(text="...").click()），因为底层环境和 UI 结构可能与你想的不同。一定要依靠 agent_cli.py 驱动手机自动生成！

- 在编写 --goal 时，一定要明确写出最后的断言是什么。例如：“最后需要断言页面上出现了'登录成功'的文字”。

- 当你需要把这个 CLI 接到更大的 Agent 工作流里时，优先使用 `--json`，不要依赖人类日志字符串做解析。
- 若你需要恢复失败上下文或把产物交给上层 Agent 继续处理，优先读取 `summary.json` 中的 `failure_analysis` 与 `pytest_asset`，以及 `pytest_replay.json` 中汇总好的 `resume_commands`。
