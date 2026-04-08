# ScreenForge CLI - 使用参考手册

欢迎 Super Agent。`ScreenForge` 是一个提供多端 UI 驱动、智能探索、自愈执行与测试代码生成能力的自动化引擎。作为外部主控大脑，你可以通过调用 `ScreenForge` 提供的 CLI 工具，完成端到端的自动化测试用例编写。

# 🛠️ 你的核心工具 (Skill)

你目前拥有以下本地命令行工具可以调用：

## 1. `agent_cli.py` (全自动 UI 探索与脚本生成器)

这个工具接收一个宏观目标，会自动连接目标端（Android / iOS / Web），分析 UI，进行点击、输入并自动生成基于 Pytest 和 Allure 的测试代码。若追加 `--json`，它还会向 stdout 输出结构化事件流，并在 `report/runs/<run_id>/` 下落盘运行摘要。

**调用语法:**

```python
python agent_cli.py --goal "<你的测试目标>" --context "<(可选)包含详细约束的文件路径>" --env "<(可选)dev/prod>" --platform "<(可选)android/ios/web>" [--vision] [--json]
```

**调用示例:**

```python
python agent_cli.py --goal "验证用户使用错误密码登录时，会出现'密码错误'的提示" --context "./docs/login_prd.md" --platform android --json
```


# 🧠 你的工作流 (Workflow)

当人类让你“根据 PRD 编写一个登录模块的自动化测试用例”时，请严格遵循以下步骤：

1. 分析与理解: 阅读用户提供的 PRD 或 Git Diff 文件，拆解出需要测试的核心业务流。

2. 生成任务描述: 将业务流转换为一段清晰的、包含前置条件和预期断言的 goal（目标）。

3. 调用底层引擎: 执行 `python agent_cli.py --goal "..."`，并将详细要求写入一个临时文件通过 `--context` 传入。若你需要稳定解析执行过程，请追加 `--json`。

4. 验证生成结果: 命令执行完毕后，读取输出脚本，并同步检查 `report/runs/<run_id>/summary.json` 与 `steps.jsonl`，确认退出码、最终状态和关键步骤是否符合预期。

5. 归档与重命名: 如果你没有显式传入 `--output`，底层引擎会按平台和时间戳自动命名。若代码正常，你可以再使用 shell 命令重命名为更有业务语义的文件名。

6. 运行验收: 执行 pytest test_cases/test_login_failure.py 验证脚本的可执行性。

# ⚠️ 注意事项与约束

- 千万不要手动修改生成的 test_cases/*.py 中的 UI 定位器（如 d(text="...").click()），因为底层环境和 UI 结构可能与你想的不同。一定要依靠 agent_cli.py 驱动手机自动生成！

- 在编写 --goal 时，一定要明确写出最后的断言是什么。例如：“最后需要断言页面上出现了'登录成功'的文字”。

- 当你需要把这个 CLI 接到更大的 Agent 工作流里时，优先使用 `--json`，不要依赖人类日志字符串做解析。
