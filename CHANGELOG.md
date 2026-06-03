# Changelog

All notable changes to ScreenForge will be documented in this file.

## [Unreleased]

### Changed (BREAKING)
- **`assert_exist` / `assert_text_equals` now report real pass/fail.** Previously
  both always "passed" (the engine generated assertion code but never failed the
  step), so `--goal` verification and `--action` assert steps could never fail.
  A failing assertion now returns a failed step. In `--json` output, assertion
  failures carry `"result": "assertion_failed", "assertion_failed": true` to
  distinguish a verification verdict from an engine error — agents should report
  these as test failures, not retry them.

### Fixed
- **Web recording crash removed; recording documented as unsupported**:
  `stop_record_and_get_path` called `self.driver.video.path()` which is `None`
  when no `record_video_dir` was set, raising under some paths. Web video
  recording is in fact impossible here — the adapter attaches over CDP
  (`connect_over_cdp`) and Playwright cannot record a CDP-attached browser
  (verified: `page.video` exists but no file is written). The CLI never wired web
  recording anyway (only iOS records). So `start_record`/`stop_record` are now
  honest no-ops returning `""`, and the dead `record_video_dir` branch + unused
  `_find_chromium_path` are removed.
- **Broken install command**: docs and `doctor`'s remediation told users to run
  `pip install -r requirement.txt`; the file is `requirements.txt`.
- **7 failing tests** from the `agent_cli.py` shim refactor — tests now target
  the real modules (`cli.tool_protocol_handlers` / `cli.shared` / `cli.dispatch`).
- **ML stack made truly optional**: `sentence_transformers` (the ~2GB torch
  stack) was imported at module load, so a clean core-only install crashed at
  `import common.ai`. Now imported lazily inside `EmbeddingModelLoader.load()`;
  the semantic cache degrades gracefully (exact-key cache still works) when the
  `[ml]` extra isn't installed. torch/transformers/sentence-transformers/
  scikit-learn moved out of core `requirements.txt`.
- **MCP web ref cache leak**: the process-global `_cached_ui_elements` could
  serve stale `@N` from a prior page/request. `inspect_ui` now syncs the cache
  to the page just inspected, and web ref resolution always re-inspects the live
  page.
- **`not_found` no longer trips the circuit breaker**: in `--goal` mode the
  model's `not_found` signal is intercepted (suggest `--vision`) without counting
  as a failure.
- Dead `common/prompts.py` (172 LOC, zero importers, diverged from the live
  brains) deleted; dead `_find_chromium_path` removed.
- `config.validate_config` now bounds-checks `AUTO_HEAL_MIN_CONFIDENCE` (0-1) and
  `AUTO_HEAL_TRIGGER_THRESHOLD` (>= 1).
- **`--web-stop` now reliably kills the browser** (caught by the new live smoke):
  CDP-attached Chromium ignores `SIGTERM`, so the reaper escalates to `SIGKILL`
  after a grace period; `_is_process_alive` now treats a `Z`/defunct zombie as
  not-alive (an unreaped corpse was being mistaken for a live browser).
- **iOS `swipe` crashed** (caught by the live iOS simulator smoke): `SwipeHandler`
  called `d.swipe_ext(direction)` — a uiautomator2 (Android) API — on every
  non-web platform, so swipe raised `AttributeError: 'Client' object has no
  attribute 'swipe_ext'` on iOS. Now uses facebook-wda's directional
  `swipe_up/down/left/right()`. Verified on a real simulator: all four directions
  work. (Invalid directions safely default to `down`.)
- **Android `resourceId` locator was completely unusable** (caught by expanding
  the live Android smoke to the click/input/swipe/press verbs): the XML
  compressor stripped the package prefix, emitting a bare `search_src_text` while
  uiautomator2's `resourceId` selector matches the full `pkg:id/name`. So every
  resourceId the agent received (its #2-priority Android locator) matched zero
  elements. The compressor now emits the full resource-id (+ an optional
  `id_short` hint). Verified on a real device: `input` via the full id now works.
- **Android assert/action on an absent element wrongly reported success**
  (caught by the new live Android smoke): `execute_and_record` gated execution on
  `element` truthiness, but uiautomator2's `UiObject` is *falsy* when it matches
  0 elements — so the handler (and its wait) was skipped and the step returned a
  fast false success. Now gates on `element is not None`, so the handler runs and
  reports the real verdict. Affects every element action on a transiently-absent
  android element, not just asserts.

### Added
- `test_public_surface.py` — pins the CLI package's public symbols so future
  refactors that drop a name fail fast at the contract.
- **Per-platform locator matrix** in `--capabilities` (`locators` / `features`):
  ref/bbox/screenshot-annotation/visual-fallback are now correctly reported as
  Web-only (mobile docs previously over-claimed them as universal).
- `--web-stop` — terminate the persistent Chromium (CDP port 9333) left running
  by web runs; idempotent.
- **Live smoke tests against real hardware**, all opt-in and skipped by default:
  - `test_web_smoke_live.py` (`RUN_LIVE_WEB_SMOKE=1`) — real Chromium: launch /
    inspect+ref / assert / `--web-stop`. Caught the SIGTERM/zombie bug above.
  - `test_android_smoke_live.py` (`RUN_LIVE_ANDROID_SMOKE=1`) — real device via
    uiautomator2: setup / live UI-tree / assert contract. Caught the falsy
    `UiObject` bug above.
  - `test_ios_smoke_live.py` (`RUN_LIVE_IOS_SMOKE=1`) — booted simulator: the
    `simctl` session-recording reaper (WDA-dependent adapter checks self-skip).
  These exist because mock-only tests passed while the real features were broken;
  the smokes make "green in mocks, broken on hardware" fail loudly.

### Docs
- Corrected `capability-matrix.md` / `agent_guide.md`: ref/bbox/visual fallback
  are Web-only; `--capabilities` is the machine-readable source of truth.
- Documented the `--json` assertion-failure contract and the persistent-browser
  lifecycle.

## [0.2.1] - 2026-05-25

### Added
- **iOS adapter rewrite**: WDA health checks, session reconnect, `xcrun simctl` screen recording, auto-detect booted simulator UDID
- **Android adapter rewrite**: session persistence across CLI calls, auto-reconnect on disconnect, structured error codes (E050–E055)
- **Session mode** (`--session-id` / `--session-end`): group multiple `--action` calls into one test file and one recording; PID-based cross-process recording lifecycle
- **`--json` action output**: single-line JSON on stdout with `ok`, `action`, `ui_tree`, `element_count` — enables action + inspect in one call
- **iOS UI tree compressor** (`utils/utils_ios.py`): filters keyboard keys, single-digit noise, scroll bars, deduplicates; reduces 123 elements to ~49
- **iOS executor support**: locator mapping (text→label, resourceId→name) and press key handling with keyboard button fallback
- **Device targeting flags**: `--device-url` (WDA URL override), `--device-serial` (Android serial / iOS UDID override)
- **Mobile setup guide** (`docs/mobile-setup.md`): Android & iOS device connection instructions

### Fixed
- Infinite recursion in `take_screenshot()` reconnect (both adapters) — now guards with `_retry` flag
- Reporter event noise in `--json` mode — action mode suppresses reporter stdout via `json_output=False` kwarg
- iOS scroll bar filter now handles both Chinese ("滚动条") and English ("scroll bar") locales
- `cli/shared.py` no longer imports from `main.py` — inlined `get_initial_header`, `save_to_disk`, `launch_app`

## [0.2.0] - 2026-05-25

### Added
- **Playground live viewer**: `screenforge --playground` launches a web UI at localhost:7860 showing real-time browser screenshots and action history via SSE
- **CDP Screencast integration**: Playground auto-connects to Chrome DevTools Protocol and streams live frames — no manual screenshot pushing needed
- **GitHub Action**: `uses: jhinzzz/ScreenForge@v1` adds ScreenForge to any CI pipeline with auto Playwright install and Allure artifact upload
- **`screenforge --init` wizard**: interactive first-time setup (platform selection, LLM config, dependency checks)
- **MCP setup guide** (`docs/mcp-setup.md`): 3-minute configuration for Claude Desktop, Cursor, Cline, and Claude Code
- **Launch kit** (`docs/launch-kit.md`): ready-to-post templates for Show HN, Reddit, and Twitter
- **English workflow examples**: `web_login.yaml`, `web_search.yaml`, `web_form_submit.yaml` in `docs/workflows/`
- **Rich progress spinners**: AI calls and action execution show animated status in terminal (auto-disabled in tool/MCP mode)
- **Rich doctor table**: `--doctor` displays color-coded pass/fail table in interactive terminals
- **Demo GIF**: `scripts/demo.tape` generates the README demo via VHS
- **README badge**: shields.io badge for projects using ScreenForge-generated tests
- **Optional `[playground]` extra**: `pip install screenforge[playground]` (fastapi + uvicorn + websockets)

### Changed
- **`.env_template`**: defaults to OpenAI endpoint (`api.openai.com/v1`, `gpt-4o`) instead of vendor-specific Chinese endpoint
- **Error messages list valid options**: invalid `--action` now shows all supported actions
- **Doctor uses relative paths**: remediation docs references no longer leak absolute filesystem paths

### Fixed
- `scripts/demo.tape` activates venv and runs `pip install -e .` to ensure `screenforge` CLI is available

## [0.1.1] - 2026-05-25

### Security
- **Code-generation injection hardening**: `_escape_locator_value` now escapes `\n`, `\r`, `\t`, `\0` in addition to quotes/backslashes — prevents injecting arbitrary Python through crafted locator values
- **Release pipeline pinned**: `pypa/gh-action-pypi-publish` pinned to SHA (`fb13cb30...`) instead of floating `release/v1` tag — mitigates supply-chain attacks
- **Tag-version consistency check**: release workflow now verifies git tag matches `cli/_version.py` before publishing

### Added
- Unit tests for CLI core paths: runtime_modes, capabilities, shorthand, parser, run_resume, run_reporter, dispatch (32 → 180 tests)
- Type-safe `SimpleNamespace` fixtures in dispatch tests (replaces MagicMock)
- AI brain and cache manager integration tests
- Pre-publish test step in release pipeline
- Pre-commit hooks: ruff (lint+format) + mypy
- `screenforge --demo` shorthand command
- `screenforge inspect` / `screenforge click "Login"` shorthand CLI preprocessor
- `.github/workflows/ci.yml` with automated pytest on push/PR

### Changed
- Complete English-first translation: all developer-facing logs, CLI output, preflight hints, MCP error messages
- Narrowed failure classification tokens to prevent false-positive categorization
- `MCP_SERVER_VERSION` now sourced from `cli/_version.py` (was hardcoded, could drift)
- `cli/dispatch.py` uses `json.dumps` for JSON construction (was f-string, fragile)
- Removed dead code `inject_inspect_stdin()` from shorthand module

### Fixed
- `--doctor` output was still Chinese — all hints translated to English
- `--capabilities` leaked absolute filesystem paths — now uses relative paths

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
