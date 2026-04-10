---
name: diagnose
description: Run environment diagnostics and troubleshoot ScreenForge setup issues. Use when the user reports connection failures, missing dependencies, or wants to verify their environment is ready.
disable-model-invocation: false
user-invocable: true
allowed-tools: Bash(python agent_cli.py *) Bash(source .venv/bin/activate *) Bash(adb *) Bash(curl *) Bash(pip *)
argument-hint: "[platform: android|ios|web]"
---

# ScreenForge Environment Diagnostics Skill

检查 ScreenForge 运行环境是否就绪，定位连接问题。

## 运行诊断

```bash
source .venv/bin/activate && python agent_cli.py --doctor --platform android
source .venv/bin/activate && python agent_cli.py --doctor --platform web
source .venv/bin/activate && python agent_cli.py --doctor --platform ios
```

Doctor 输出 `doctor_summary` 分组诊断事件，包含 `fix_command`、`fix_doc` 和 `fix_doc_section`。

## 快速查看已落地能力

```bash
source .venv/bin/activate && python agent_cli.py --capabilities
```

## 按平台排障

### Android

| 症状 | 修复 |
|------|------|
| `uiautomator2` 缺失 | `pip install -r requirement.txt` |
| `adb_devices` 失败 | 执行 `adb devices` 确认设备在线、USB 调试已开启且已授权 |
| `adb` 不在 PATH | 安装 Android Platform Tools，重新打开终端 |
| ATX 未初始化 | `python -m uiautomator2 init`（手机上点"允许"） |
| 受限沙箱报 adb 端口受限 | 在宿主终端直接执行 `adb devices` 确认 |

### Web

| 症状 | 修复 |
|------|------|
| `playwright` 缺失 | `pip install playwright` |
| CDP 端点不可达 | 确认 Chrome 以 `--remote-debugging-port=9222` 启动 |
| `WEB_CDP_URL` 不合法 | 检查 `.env` 中的 `WEB_CDP_URL` 格式 |
| 受限沙箱报 TCP 受限 | 在宿主终端执行 `curl -sS http://localhost:9222/json/version` |

### iOS

| 症状 | 修复 |
|------|------|
| `wda` 缺失 | `pip install facebook-wda` |
| `wda_status` 失败 | 确认 WebDriverAgent 已在真机启动，8100 端口可访问 |

### 通用

| 症状 | 修复 |
|------|------|
| `OPENAI_API_KEY` 未配置 | 检查 `.env` 文件，参考 `.env_template` |
| `venv_consistency` 问题 | `python scripts/repair_venv.py` |
| `runtime_paths` 问题 | 确认 `test_cases/` 与 `report/runs/` 可写 |

## 沙箱/受限环境注意

在受限 Agent 沙箱中运行 doctor 时，本地端口检查和 adb daemon 可能被阻断，这是**假阴性**，不代表设备或浏览器故障。应在宿主终端直接复核。
