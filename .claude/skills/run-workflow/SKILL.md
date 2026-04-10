---
name: run-workflow
description: Execute a YAML workflow file for multi-step UI automation. Use when the user has a workflow file or wants to batch multiple UI steps into a single structured execution.
disable-model-invocation: false
user-invocable: true
allowed-tools: Bash(python agent_cli.py *) Bash(source .venv/bin/activate *) Bash(cat *) Read
argument-hint: "[workflow.yaml path]"
---

# ScreenForge Workflow Execution Skill

用 YAML 定义多步 UI 操作，一次执行。适合沉淀高频、稳定的业务流程。

> `agent_cli.py` 是 6 行 shim，真实逻辑在 `cli/` 包内。

## Workflow YAML 格式

```yaml
version: "1"
name: login_failure
platform: android          # 可选，不写则由 --platform 指定
vars:
  username: "test_user"    # 变量，可被 --workflow-var 覆盖
  password: "wrong_pass"
  submit_label: "登录"
  error_text: "密码错误"

steps:
  - action: input
    locator_type: text
    locator_value: 用户名
    extra_value: "{{ username }}"

  - action: input
    locator_type: text
    locator_value: 密码
    extra_value: "{{ password }}"

  - action: click
    locator_type: text
    locator_value: "{{ submit_label }}"

  - action: assert_exist
    locator_type: text
    locator_value: "{{ error_text }}"
```

示例文件：`docs/workflows/login_failure.yaml`

## 执行流程

### 1. 预览计划（不执行物理动作）

```bash
source .venv/bin/activate && python agent_cli.py \
  --workflow ./docs/workflows/login_failure.yaml \
  --plan-only --platform android
```

输出每个步骤的名称和预期动作，不连接设备。

### 2. 模拟执行（连接设备但不执行物理动作）

```bash
source .venv/bin/activate && python agent_cli.py \
  --workflow ./docs/workflows/login_failure.yaml \
  --dry-run --platform android
```

连接设备，检查每个步骤的定位器是否能在当前页面解析。报告 `resolvable` / `resolution_error`。

### 3. 正式执行

```bash
source .venv/bin/activate && python agent_cli.py \
  --workflow ./docs/workflows/login_failure.yaml \
  --output "test_cases/test_login_failure.py" \
  --platform android
```

### 4. 变量覆盖

```bash
source .venv/bin/activate && python agent_cli.py \
  --workflow ./docs/workflows/login_failure.yaml \
  --workflow-var username=qa_user --workflow-var password=123456 \
  --output "test_cases/test_login.py" --platform android
```

### 5. 验证生成脚本

```bash
source .venv/bin/activate && python -m pytest test_cases/test_login_failure.py
```

## 退出码

- `0`: 所有步骤执行成功，脚本已生成
- `1`: 某个步骤执行失败，查看日志中的 `❌` 定位失败步骤

## 运行产物

- `report/runs/<run_id>/summary.json`: 运行摘要（含 `workflow_summary`）
- `report/runs/<run_id>/steps.jsonl`: 结构化事件流
- `--output` 指定路径: 生成的 pytest 脚本

## 何时用 workflow vs action

| 场景 | 推荐 |
|------|------|
| 多步确定性流程（登录、下单、注册） | `--workflow` |
| 单步探索或验证 | `--action` |
| 需要动态决策的复杂场景 | `inspect_ui` + `--action` 循环 |
