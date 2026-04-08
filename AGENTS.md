# AGENTS.md

## Build & run

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies (note: requirement.txt not requirements.txt)
pip install -r requirement.txt

# Initialize Android device (first time only)
python -m uiautomator2 init

# Interactive recording mode
python main.py

# Autonomous agent mode
python agent_cli.py --goal "..." --output "test_cases/android/test_xxx.py" --platform android
python agent_cli.py --goal "..." --output "test_cases/ios/test_xxx.py" --platform ios
python agent_cli.py --goal "..." --output "test_cases/web/test_xxx.py" --platform web [--vision] [--max_retries 3] [--context file.txt]
```

Copy `.env_template` to `.env` and fill in required variables before running.

Required env vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MODEL_NAME`, `VISION_API_KEY`, `VISION_BASE_URL`, `VISION_MODEL_NAME`

Optional env vars: `AUTO_HEAL_ENABLED`, `AUTO_HEAL_TRIGGER_THRESHOLD`, `DEFAULT_TIMEOUT`, `CACHE_ENABLED`, `CACHE_TTL_DAYS`

`config.validate_config()` must be called at startup — it exits with an error if required config is missing.

## Test

```bash
# Run all tests
pytest

# View allure report
allure serve ./report/allure-results
```

`pytest.ini` configures: `testpaths=test_cases`, `python_files=test_*.py`, flags `-vs -q --alluredir=./report/allure-results --clean-alluredir`

Exit codes: `0` = success, `1` = failure or circuit breaker triggered (agent_cli.py).

## Code style

- Use `loguru` for all logging — never use `print` or the standard `logging` module.
- Use `pydantic` for data validation and models.
- Use `typer` for CLI interfaces.
- All new platform adapters must subclass `base_adapter.py` abstract base class in `common/adapters/`.
- All configuration must be driven by `.env` / environment variables via `config/config.py` — no hardcoded values.

## Project structure

```
config/config.py          # Global config, all values from env vars
common/ai.py              # Single-step AI call + cache
common/ai_autonomous.py   # Autonomous reasoning brain (self-heal, multimodal, memory)
common/ai_heal.py         # AI self-healing module
common/executor.py        # Action executor + Python code generation
common/cache/             # L1/L2 hybrid semantic cache
common/adapters/          # Platform adapters (android / ios / web)
utils/utils_xml.py        # Android XML cleaning and dimensionality reduction
utils/utils_web.py        # Web utility functions
test_cases/               # Auto-generated test scripts (android / ios / web)
docs/                     # Agent guides and skill descriptions
```

## Other conventions

- Dependency file is `requirement.txt` (not `requirements.txt`).
- Auto-generated test files follow the naming pattern `test_auto_<YYYYMMDD_HHMMSS>.py` and are placed under `test_cases/<platform>/`.
- Do not commit `.env` files; use `.env_template` as the reference.
- `conftest.py` at project root handles cross-platform fixture dispatch and attaches video/screenshot artifacts to Allure reports.

## 第一性原则

从需求和问题本质出发，不从惯例或模板出发。

1. 不要假设我清楚自己想要什么。动机或目标不清晰就停下来讨论。
2. 目标清晰但路径不是最短的，直接告诉我并建议更好的办法。
3. 遇到问题追根因，不打补丁。每个决策都要能回答"为什么"。
4. 输出说重点，砍掉一切不改变决策的信息。

## Documentation Conventions

### specs/

历次迭代的文档，每次迭代一个文件夹，包含：

- 1-requirements.md - 需求文档
- 2-research.md - 调研文档（简单变更可省略）
- 3-tech-design.md - 技术设计文档
- 4-test-case.md - 测试用例文档（统一管理单元测试、白盒测试、集成测试）
- 5-test-task.md - 测试任务文档（定义执行顺序、失败处理、统一报告）
- 6-tasks.md - 任务清单
- 7-review.md - 迭代复盘（迭代完成后编写）

### docs/

项目汇总文档，根据每次迭代整理，始终反映最新状态：

- requirements-overview.md - 需求概览
- tech-arch-overview.md - 技术架构概览
- tech-design-overview.md - 技术设计概览
- tech-api-overview.yaml - API 接口概览（OAS 3.1）
- tech-memory-overview.md - 技术记忆与知识
- tech-rule-overview.md - 技术规范

## API Documentation (OAS 3.1)

docs/tech-api-overview.yaml 采用 OpenAPI 3.1 标准，维护时须遵守：

### 数据来源
- HTTP API：从项目路由注册（gin/echo/chi/FastAPI 等）扫描，追踪 handler 返回的 struct/class 递归展开所有字段（含 JSON tag、validate tag）
- gRPC：从 .proto 文件扫描，放入 x-grpc-services 扩展字段
- 部署信息：从 charts/ 下所有环境子目录扫描域名、认证、gRPC 端口

### Schema 规则（强制）
1. 所有 type: object 必须包含 properties，禁止空 object 占位符
2. 所有 type: array 的 items 必须有 properties 或 $ref，禁止空 object
3. 所有 $ref 引用必须在 components/schemas 中存在且完整展开
4. 外部类型（protobuf/外部包 struct）必须追溯源码获取字段，禁止凭印象编写
