# Contributing to ScreenForge

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/jhinzzz/ScreenForge.git
cd ScreenForge
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
pip install ruff
```

## Running Tests

```bash
# Unit tests (no device needed, ~0.6s)
pytest tests/ -q

# Include integration test_cases (requires devices/browser)
pytest tests/ test_cases/ -q

# Lint
ruff check .

# Environment diagnostics
screenforge --doctor --platform web
```

## Shorthand Commands (Development)

```bash
# These are equivalent:
screenforge click "Login"                    # shorthand
screenforge --action click --locator-type text --locator-value "Login"  # full

# CSS selectors auto-detected
screenforge click "#email"                   # → --locator-type css
screenforge input "#email" "admin@test.com"  # → --locator-type css + --extra-value

# Global actions (no locator needed)
screenforge goto "https://example.com"
screenforge press "Enter"
screenforge swipe up

# Inspect current page
screenforge inspect
```

## Code Style

- **Logging**: Use `loguru` via `from common.logs import log`. Never use `print()` or stdlib `logging`.
- **Config**: All config from env vars via `config/config.py`. No hardcoded values.
- **Error messages**: English, three-tier format: `[EXXX] What happened. Why. Fix: <command>`
- **Data models**: Use `pydantic` for validation.
- **Adapters**: All platform adapters subclass `BasePlatformAdapter` in `common/adapters/`.

## Commit Message Format

```
<type>: <short description>

type = feat | fix | refactor | test | docs | chore
```

Examples: `feat: add workflow variable interpolation`, `fix: narrow failure classification token`

## Pull Request Process

1. Fork and create a branch from `main`
2. Make your changes
3. Ensure `pytest tests/` and `ruff check .` pass
4. New code should include unit tests in `tests/`
5. Submit a PR using the template

## Error Code Ranges

When adding new error messages, use the appropriate range:

| Range | Module |
|-------|--------|
| E001-E009 | Config validation |
| E010-E019 | CLI dispatch |
| E020-E029 | Execution modes (default/action/workflow) |
| E030-E039 | Executor (action handling) |
| E040-E049 | Adapters (platform connection) |
| E050-E059 | AI/LLM interaction |

## Architecture

```
Your Agent (brain) ──► ScreenForge (hands)
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
          AIBrain      UIExecutor    HistoryManager
              │             │
        CacheManager   ActionHandler
                            │
                   BasePlatformAdapter
                 (Android / iOS / Web)
```

ScreenForge does NOT make decisions. It executes actions from the upstream Agent and generates pytest scripts.

## Questions?

Open a [Discussion](https://github.com/jhinzzz/ScreenForge/discussions) for questions, or file an [Issue](https://github.com/jhinzzz/ScreenForge/issues) for bugs.
