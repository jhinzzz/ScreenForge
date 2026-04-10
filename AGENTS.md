# AGENTS.md

## Agent Protocol

**你是大脑，ScreenForge 是手脚。**

当用户要求你操作 UI（打开网页、点击按钮、填写表单、执行测试等），你必须：
1. **自己理解**用户的 PRD / 自然语言意图
2. **调用 `inspect_ui`** 获取当前真实 UI 树（DOM/XML）
3. **自己分析** UI 树，定位目标元素
4. **逐步下发 `action` 指令**让 ScreenForge 执行

```bash
# 获取当前页面 UI 树（你来分析，不是让别的 LLM 分析）
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin

# 你分析完 UI 树后，下发精确的单步动作
python agent_cli.py --action goto --platform web --extra-value "https://example.com"
python agent_cli.py --action click --platform web --locator-type text --locator-value "Login"
python agent_cli.py --action input --platform web --locator-type css --locator-value "#username" --extra-value "admin"

# 每步执行后再次 inspect_ui，确认页面状态，决定下一步
```

### 支持的 action 类型

| action | 说明 | 需要 locator | 需要 extra_value |
|--------|------|:---:|:---:|
| `goto` | 导航到 URL（仅 Web） | 否 | URL |
| `click` | 点击元素 | 是 | 否 |
| `long_click` | 长按元素 | 是 | 否 |
| `hover` | 悬停元素（Web 端） | 是 | 否 |
| `input` | 输入文本 | 是 | 输入内容 |
| `swipe` | 滑动屏幕 | 否 | up/down/left/right |
| `press` | 模拟按键 | 否 | 按键名(Enter/Back) |
| `assert_exist` | 断言元素存在 | 是 | 否 |
| `assert_text_equals` | 断言文本一致 | 是 | 期望文本 |

locator_type 优先级：`css` > `resourceId` > `text` > `description`

### 禁止事项

- **禁止使用 `--goal`**：该入口会调第三方 LLM 替你思考，浪费 token 且效果差
- **禁止凭空编写 UI 代码**：必须先 `inspect_ui` 拿到 DOM 树再定位
- **禁止把自然语言原样透传**：你负责理解需求，ScreenForge 只负责执行动作

详细集成文档见 `docs/agent_guide.md`。

## Build & run

```bash
source .venv/bin/activate
pip install -r requirement.txt       # 注意: requirement.txt 不是 requirements.txt
python -m uiautomator2 init          # Android 首次初始化
python main.py                       # 人类交互式录制
```

Copy `.env_template` to `.env` and fill in required variables before running.

Required env vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MODEL_NAME`, `VISION_API_KEY`, `VISION_BASE_URL`, `VISION_MODEL_NAME`

Optional env vars: `AUTO_HEAL_ENABLED`, `AUTO_HEAL_TRIGGER_THRESHOLD`, `DEFAULT_TIMEOUT`, `CACHE_ENABLED`, `CACHE_TTL_DAYS`

## Test

```bash
pytest                                # Run all tests
allure serve ./report/allure-results  # View allure report
```

`pytest.ini` configures: `testpaths=tests test_cases`, `python_files=test_*.py`

Exit codes: `0` = success, `1` = failure or circuit breaker triggered.

## Code style

- Use `loguru` for all logging — never `print` or standard `logging`.
- Use `pydantic` for data validation and models.
- All new platform adapters must subclass `common/adapters/base_adapter.py`.
- All configuration via `.env` / environment variables via `config/config.py` — no hardcoded values.

## Project structure

```
agent_cli.py              # 兼容入口 (6 行 shim，委托 cli/dispatch.py)
main.py                   # 人类交互式录制引擎
cli/                      # CLI 真实分发层
  dispatch.py             # CLI 入口 main()
  parser.py               # 参数解析与校验
  shared.py               # 懒加载代理、适配器连接、UI 状态抓取
  reporter.py             # 报告辅助
  doctor.py               # 环境体检
  tool_protocol_handlers.py  # --tool-stdin / --tool-request / --mcp-server
  modes/                  # 各执行模式 (default/action/workflow/plan/dry_run)
config/config.py          # 全局配置 (API Keys, 超时, 自愈阈值)
common/ai.py              # 单步 AI 调用 + 缓存
common/ai_autonomous.py   # 自主推理大脑
common/ai_heal.py         # 结构化自愈引擎 (HealResult, AST 校验)
common/executor.py        # 动作执行器 + 代码生成
common/visual_fallback.py # 视觉 fallback (VLM 坐标解析)
common/cache/             # L1/L2 混合语义缓存
common/adapters/          # 平台适配器 (android / ios / web)
utils/utils_xml.py        # Android XML 清洗降维
utils/utils_web.py        # Web DOM 压缩
utils/screenshot_annotator.py  # 截图标注 (ref 编号叠加)
tests/                    # 框架单元测试 (32 用例)
test_cases/               # 自动生成的测试脚本 (android / ios / web)
docs/                     # Agent 集成文档与能力矩阵
```

## Other conventions

- Dependency file is `requirement.txt` (not `requirements.txt`).
- Auto-generated test files: `test_auto_<YYYYMMDD_HHMMSS>.py` under `test_cases/<platform>/`.
- Do not commit `.env` files; use `.env_template` as the reference.
- `conftest.py` at project root handles cross-platform fixture dispatch and video/screenshot Allure attachments.
