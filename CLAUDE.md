# CLAUDE.md

**[中文版](./CLAUDE_CN.md)** | English

## Agent Collaboration Protocol (Required Reading)

**You are the brain. ScreenForge is the hands.**

When a user asks you to interact with UI (open pages, click buttons, fill forms, run tests), you must:
1. **Understand** the user's PRD / natural language intent yourself
2. **Call `inspect_ui`** to get the real UI tree (DOM/XML)
3. **Analyze** the UI tree yourself, locate target elements
4. **Issue `action` commands step by step** for ScreenForge to execute

### Standard Workflow (Recommended: `--json` mode)

```bash
# 1. Get current page UI tree (YOU analyze it, not another LLM)
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin

# 2. Execute action AND get post-action UI tree in one call (--json)
python agent_cli.py --action goto --platform web --extra-value "https://example.com" --json 2>/dev/null
python agent_cli.py --action click --platform web --locator-type text --locator-value "Login" --json 2>/dev/null
python agent_cli.py --action input --platform web --locator-type css --locator-value "#username" --extra-value "admin" --json 2>/dev/null
python agent_cli.py --action press --platform web --extra-value "Enter" --json 2>/dev/null

# --json returns: {"ok": true, "action": "...", "ui_tree": {...}, "element_count": N}
# Analyze ui_tree from the response to decide next step — no separate inspect needed
```

### Multi-Step Sessions

```bash
# Group actions into one test file + continuous recording
python agent_cli.py --action click --platform ios --locator-type text --locator-value "Login" --session-id s1 --json 2>/dev/null
python agent_cli.py --action input --platform ios --locator-type text --locator-value "Email" --extra-value "user@test.com" --session-id s1 --json 2>/dev/null
python agent_cli.py --session-end s1
```

### Supported Actions

| action | Description | Needs locator | Needs extra_value |
|--------|-------------|:---:|:---:|
| `goto` | Navigate to URL (Web only) | No | URL |
| `click` | Click element | Yes | No |
| `long_click` | Long-press element | Yes | No |
| `hover` | Hover element (Web) | Yes | No |
| `input` | Type text | Yes | Input content |
| `swipe` | Swipe screen | No | up/down/left/right |
| `press` | Simulate key press | No | Key name (Enter/Back) |
| `assert_exist` | Assert element exists | Yes | No |
| `assert_text_equals` | Assert text matches | Yes | Expected text |

locator_type priority: `css` > `resourceId` > `text` > `description`

### Prohibited

- **Never use `--goal`**: It calls a third-party LLM to think for you — wastes tokens, poor results. Human manual experiments only.
- **Never write UI code without inspecting first**: You cannot see the screen. Always `inspect_ui` to get the DOM tree before locating elements.
- **Never pass natural language directly**: You are responsible for understanding requirements. ScreenForge only executes actions.

See `docs/agent_guide.md` for the full integration protocol.

## Build & Run

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize Android device (first time only)
python -m uiautomator2 init

# Human debugging / interactive recording
python main.py
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

`pytest.ini` configures: `testpaths=tests test_cases`, `python_files=test_*.py`, flags `-vs -q --alluredir=./report/allure-results --clean-alluredir`

Exit codes: `0` = success, `1` = failure or circuit breaker triggered (agent_cli.py).

## Code Style

- Use `loguru` for all logging — never use `print` or the standard `logging` module.
- Use `pydantic` for data validation and models.
- Use `typer` for CLI interfaces.
- All new platform adapters must subclass `base_adapter.py` abstract base class in `common/adapters/`.
- All configuration must be driven by `.env` / environment variables via `config/config.py` — no hardcoded values.

## Project Structure

```
agent_cli.py              # Compatibility entry (6-line shim, delegates to cli/dispatch.py)
main.py                   # Interactive recording engine for humans
cli/                      # CLI dispatch layer (real implementation)
  dispatch.py             # CLI entry main(), routes by execution mode
  parser.py               # build_parser, validate_cli_args
  shared.py               # Lazy proxies, adapter connection, UI state capture
  reporter.py             # Reporter helpers
  doctor.py               # Environment diagnostics
  tool_protocol_handlers.py  # --tool-stdin / --tool-request / --mcp-server
  modes/                  # Execution modes (default/action/workflow/plan/dry_run)
config/config.py          # Global config, all values from env vars
common/ai.py              # Single-step AI call + cache
common/ai_autonomous.py   # Autonomous reasoning brain (self-heal, multimodal, memory)
common/ai_heal.py         # Structured self-heal engine (HealResult, AST validation)
common/executor.py        # Action executor + Python code generation
common/visual_fallback.py # Visual fallback (VLM coordinate parsing)
common/cache/             # L1/L2 hybrid semantic cache
common/adapters/          # Platform adapters (android / ios / web)
utils/utils_xml.py        # Android XML cleaning and dimensionality reduction
utils/utils_web.py        # Web DOM compression and URL handling
utils/screenshot_annotator.py  # Screenshot annotation (ref numbers on screenshots)
tests/                    # Framework unit tests (278 passing, 15 live-smoke skipped)
test_cases/               # Auto-generated test scripts (android / ios / web)
docs/                     # Agent integration guide and capability matrix
```

## Other Conventions

- Dependency file is `requirements.txt`.
- Auto-generated test files follow the naming pattern `test_auto_<YYYYMMDD_HHMMSS>.py` and are placed under `test_cases/<platform>/`.
- Do not commit `.env` files; use `.env_template` as the reference.
- `conftest.py` at project root handles cross-platform fixture dispatch and attaches video/screenshot artifacts to Allure reports.

## Pre-Commit Checklist (enforce without being asked)

Before committing or opening a PR, always run these two checks — do not wait for the user to remind you:

1. **No process artifacts in the commit.** Never stage or commit working docs: `docs/superpowers/**` (plans/specs), `docs/optimization-*.md`, `specs/`, `report/`, generated `test_cases/<platform>/`, `.omc/`, `*demo*` outputs. These are `.gitignore`d — verify `git status`/`git diff --cached --name-only` is clean of them before every commit. If one is already tracked from the past, `git rm --cached` it as part of the change.
2. **Update outward-facing docs when behavior changes.** Any user-visible feature/flag/CLI change must update, in the same PR: `README.md` **and** `README_CN.md` (EN canonical, CN mirror), plus `CHANGELOG.md` **and** `CHANGELOG_CN.md` under `## [Unreleased]`. No silent feature shipping.

## First Principles

Start from the essence of the problem, not from convention or templates.

1. Don't assume I know what I want. If motivation or goal is unclear, stop and discuss.
2. If the goal is clear but the path isn't shortest, tell me directly and suggest a better approach.
3. Chase root causes, not patches. Every decision must answer "why."
4. Say what matters, cut everything that doesn't change the decision.

## Documentation Conventions

### specs/

Documents for each iteration, one folder per iteration:

- 1-requirements.md — Requirements document
- 2-research.md — Research document (optional for simple changes)
- 3-tech-design.md — Technical design document
- 4-test-case.md — Test cases (unit tests, white-box tests, integration tests)
- 5-test-task.md — Test tasks (execution order, failure handling, unified reporting)
- 6-tasks.md — Task checklist
- 7-review.md — Iteration retrospective (written after iteration completes)

### docs/

Project summary documents, maintained per iteration, always reflecting current state:

- requirements-overview.md — Requirements overview
- tech-arch-overview.md — Technical architecture overview
- tech-design-overview.md — Technical design overview
- tech-api-overview.yaml — API overview (OAS 3.1)
- tech-memory-overview.md — Technical memory and knowledge
- tech-rule-overview.md — Technical standards

## API Documentation (OAS 3.1)

docs/tech-api-overview.yaml follows OpenAPI 3.1 standard. When maintaining:

### Data Sources
- HTTP API: scan from project route registrations (gin/echo/chi/FastAPI etc.), trace handler return structs/classes and recursively expand all fields (including JSON tags, validate tags)
- gRPC: scan from .proto files, place in x-grpc-services extension
- Deployment info: scan domains, auth, gRPC ports from charts/ subdirectories

### Schema Rules (Mandatory)
1. All `type: object` must include `properties` — no empty object placeholders
2. All `type: array` items must have `properties` or `$ref` — no empty objects
3. All `$ref` references must exist in `components/schemas` and be fully expanded
4. External types (protobuf/external package structs) must trace source code for fields — never write from memory

## Skill Routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
