# Changelog

All notable changes to ScreenForge will be documented in this file.

## [Unreleased]

### Added
- Unit tests for CLI core paths: runtime_modes, capabilities, shorthand, parser, run_resume, run_reporter, dispatch (32 → 154 tests)
- Type-safe `SimpleNamespace` fixtures in dispatch tests (replaces MagicMock)

### Changed
- Complete English-first translation: all developer-facing logs in ai.py, ai_autonomous.py, cache/, case_memory.py, visual_fallback.py, utils/
- Narrowed failure classification tokens to prevent false-positive categorization

## [0.1.0] - 2026-05-22

### Added
- English-first README with Quick Start, comparison table, and architecture diagram
- `screenforge --demo` command for zero-config first experience (no API key needed)
- `screenforge --version` flag
- Three-tier error messages with error codes, explanations, and fix suggestions
- `CHANGELOG.md` for version transparency

### Changed
- Default `OPENAI_BASE_URL` now points to `https://api.openai.com/v1` (was vendor-specific)
- Default `MODEL_NAME` now `gpt-4o` (was vendor-specific)
- `VISION_MODEL_NAME` defaults to `MODEL_NAME` for elegant fallback
- `validate_config()` now uses `loguru` instead of `print()` (fixes stdout pollution in Agent integrations)
- All user-facing error messages converted to English with structured error codes
- `docs/agent_guide.md` fully translated to English

### Fixed
- Agent integrations receiving garbled stdout when config validation failed (print → log.error)
- Circuit breaker messages now include diagnostic context and recovery suggestions

## [0.0.2] - 2026-03-30

### Changed
- Extracted `EmbeddingModelLoader` from `CacheManager` for better separation of concerns
- Platform directory auto-creation in `agent_cli.py`
- Exception handling in `main.py` — no longer silently swallows errors

## [0.0.1] - 2026-03-01

### Added
- Initial release with Agentic and Interactive dual modes
- L1/L2 hybrid semantic cache system
- Cross-platform adapters (Android/iOS/Web)
- Self-healing engine with confidence scoring and AST validation
- MCP server with 5 tools
- Structured run artifacts (summary.json, steps.jsonl, artifacts.json)
