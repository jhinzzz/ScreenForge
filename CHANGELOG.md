# Changelog

All notable changes to ScreenForge will be documented in this file.

## [Unreleased]

### Fixed
- **Web DOM compressor was blind to shadow DOM and iframes** — the LLM's "eyes"
  (`compress_web_dom`) used a flat `querySelectorAll('*')` that doesn't pierce
  shadow roots or descend into iframe documents, so whole Web-Component apps and
  embedded (payment/login) frames were invisible: Playwright could click those
  elements but the model never learned they existed. The compressor now
  recursively walks open shadow DOM and same-origin/`srcdoc` iframes, offsetting
  iframe-child bounding boxes back to top-document coordinates (including the
  iframe's border + padding inset, so ref/coordinate clicks land correctly).
  Closed shadow roots and cross-origin iframes remain un-pierceable (browser
  security boundary) and are skipped honestly.
- `disabled` / `aria-disabled` controls were reported `clickable:true`, so the
  model would target them and hang on the action timeout. They are now recorded
  (for existence/disabled assertions) but marked `clickable:false` with a
  `disabled:true` flag.
- `<fieldset disabled>` did not propagate to its descendant controls — only the
  element's own `disabled` attribute was honored, so controls inside a disabled
  fieldset were reported `clickable:true` and the model would hang on them.
  "Actually disabled" is now judged via the `:disabled` CSS pseudo-class (the
  browser's authoritative implementation), covering fieldset propagation, the
  first-`<legend>` exemption, and nesting in one shot.
- Controls inside an `[inert]` subtree (the standard modal-backdrop pattern —
  everything behind an open `<dialog>`) swallow clicks but were emitted
  `clickable:true`, so the model would target a dead control behind the modal.
  They are now `clickable:false`, and the inert state is **inherited across
  shadow / same-origin iframe boundaries** (threaded through the compressor's
  recursion like the coordinate offsets). Surfaced as its own `inert:true` field,
  **not** folded into `disabled` (distinct concepts — blocked-by-overlay vs
  intrinsically-off — so an `assert disabled` won't wrongly pass).
- **Android compressor ignored `enabled`** — a control with `clickable="true"
  enabled="false"` (greyed-out button, empty SIM slot) was reported
  `clickable:true` and the model would tap a dead control and hang (the same
  blind spot the web compressor already fixed). Android now suppresses
  `clickable` and emits `disabled:true` for `enabled="false"`, still recording
  the control so its existence/disabled state stays assertable. The numeric-noise
  text filter was reordered so a disabled control with short numeric text (e.g. a
  disabled "+5" stepper) isn't silently dropped.
- **`--action --json` failures were a dead string** (`{"result":"engine_error",
  "error":"Action failed: click:Login"}`) with no page and no guidance, and the
  useful `[E0xx] Fix:` diagnostics lived only on stderr (which agent examples drop
  via `2>/dev/null`). An engine-error failure now returns a structured, recoverable
  payload: `error_code` + `fix` (from a single-source table shared with stderr, so
  they can't drift), did-you-mean `candidates` (difflib over page element
  text/desc/name, honest 0.55 threshold — below it returns nothing rather than a
  fabricated match), `recommended_next_step`, and the current `ui_tree` (so no
  second `inspect_ui` is needed). A failed assertion stays a bare verdict (no
  candidates / retry bait — a verdict is not a locate problem).

### Added
- Richer web interaction actions (close the "can't automate forms / off-viewport
  elements" gap): `scroll_into_view` (element-targeted, not blind swipe),
  `select` (native `<select>`), `upload` (file input), `double_click`,
  `right_click` (context menu), and `drag` (source = locator, target =
  `extra_value`, css/text auto-detected). Web-first — each maps to a stable
  Playwright API; they fail honestly on mobile rather than emitting a brittle
  coordinate step. The capabilities payload now advertises `web_only_actions`.
- Richer assertion vocabulary for real test generation: `assert_text_contains`
  (substring), `assert_not_exist` (element gone/hidden), `assert_value` (form
  field value), and `assert_url` (web page URL contains substring, a global
  no-locator action). Plus `wait_for` — an explicit synchronization action
  (`extra_value` = `visible`/`hidden`) to replace blind waits.
- Generated web tests now use Playwright's auto-retrying `expect()` assertions
  (`to_have_text` / `to_contain_text` / `to_be_hidden` / `to_have_value` /
  `to_have_url`) instead of read-once comparisons — eliminates the async-UI
  flakiness where a value is read before it settles.
- **Duplicate-named control disambiguation.** N list rows each with an identical
  "Delete" button compressed to N indistinguishable elements, so codegen could
  only emit `get_by_text('Delete').first` — silently always hitting row 1
  regardless of which the model meant. The compressor now flags only *ambiguous*
  controls (whose role+name collides with a sibling) with `scope` (the row's
  distinguishing leaf text) and `dup_index`, costing zero tokens on
  non-ambiguous pages. Codegen emits a scoped locator
  `get_by_text(scope, exact=True).locator('..').<inner>` — **no `.first`**,
  strict-mode catches non-uniqueness. When a row can't be disambiguated, an honest
  `pytest.skip` is emitted rather than a lying `.first`/`.nth`.
- `current_url` is now included in the `--action --json` success payload and the
  `inspect_ui` payload (web only; mobile honestly returns `""`) — the one read
  primitive agents actually needed, without a separate query operation.
- MCP `execute` failures carry a minimal `failure_diagnosis` (`error_code` +
  `fix` from the same single-source table; no candidates, as the run-report path
  has no live element tree).

### Changed
- `goto` no longer emits a hardcoded `wait_for_timeout(2000)`; it synchronizes
  via `goto(wait_until='load')` and relies on the next action's locator
  auto-wait (Playwright's recommended readiness strategy). `press`/`swipe`
  generated code likewise drop their fixed sleeps.
- Generated test files no longer carry an unused `import pytest` (was F401-dirty
  under ruff).
- Generated tests are now named after the user's goal/action/workflow
  (`def test_<slug>`) with the intent in the docstring + `allure.story`, instead
  of an opaque `test_auto_generated_case`. Unicode goals (e.g. Chinese) are
  preserved; symbols-only/blank labels fall back safely.
- Web codegen never bakes a pixel `mouse.click(x, y)` into a persisted test.
  When a `@N` ref can't resolve by id/text, the runtime recovers a stable
  locator (id > name > role+name > label > placeholder > text) from the
  element's remaining attributes, validates it against the live page, and
  re-drives the action's own handler (an input stays an input). When no durable
  locator exists, an honest `pytest.skip` is emitted (and for the pure VLM
  visual fallback, which has no DOM node) rather than a coordinate that rots
  silently. `allure.step` labels now show the resolved target, not a raw `@N`.
- iOS compressor unified its disabled key from the legacy `enabled:false` to
  `disabled:true`, matching Android and Web — the single LLM brain now sees one
  "can't interact" vocabulary across every platform.

### Docs
- Documented (and pinned with a live test) that virtualized lists (react-window)
  only render the viewport slice — the compressor honestly reports what's in the
  DOM, and a `scroll` + re-inspect surfaces the next slice. Not a bug; not
  force-rendered (a token blowup would be the regression).
- `agent_guide.md` shows the enriched failure payload and notes that with `--json`
  the `error_code` + `fix` ride in stdout, so dropping stderr (`2>/dev/null`) is
  safe for machine use but hides the human-readable fix hints when debugging.
- `capability-matrix.md` documents the failure-feedback ergonomics, the
  did-you-mean honesty boundaries, `current_url`, and the cross-platform
  `disabled:true` schema.

## [0.3.0] - 2026-06-04

### Changed (BREAKING)
- `assert_exist` / `assert_text_equals` now report real pass/fail. Assertion
  failures carry `"result": "assertion_failed", "assertion_failed": true` in
  `--json` output.

### Fixed
- Removed web recording crash; `start_record`/`stop_record` are now no-ops
  returning `""` (web recording is unsupported). Removed the dead
  `record_video_dir` branch and `_find_chromium_path`.
- Fixed install commands in docs and `doctor` remediation; per-platform
  remediation now points at editable extras (`pip install -e ".[android]"` /
  `".[ios]"` / `pip install -e .`).
- Fixed 7 failing tests from the `agent_cli.py` shim refactor; tests now target
  `cli.tool_protocol_handlers` / `cli.shared` / `cli.dispatch`.
- Made the ML stack optional: `sentence_transformers` is now imported lazily in
  `EmbeddingModelLoader.load()`. Moved torch/transformers/sentence-transformers/
  scikit-learn out of core `requirements.txt`.
- Fixed MCP web ref cache leak: the `@N`→element cache now lives on the
  `UIExecutor` instance instead of a process-global, with one executor per
  platform via `_SharedAdapterManager`. Ref resolution threaded through an
  explicit `resolve_ref` callable.
- `not_found` no longer trips the circuit breaker in `--goal` mode.
- Deleted dead `common/prompts.py`; removed dead `_find_chromium_path`.
- `config.validate_config` now bounds-checks `AUTO_HEAL_MIN_CONFIDENCE` (0-1) and
  `AUTO_HEAL_TRIGGER_THRESHOLD` (>= 1).
- `--web-stop` now reliably kills the browser: the reaper escalates to `SIGKILL`
  after a grace period, and `_is_process_alive` treats a `Z`/defunct zombie as
  not-alive.
- Fixed iOS `swipe` crash: now uses facebook-wda's `swipe_up/down/left/right()`
  instead of the Android-only `swipe_ext`.
- Fixed Android `resourceId` locator: the XML compressor now emits the full
  resource-id (+ optional `id_short` hint).
- Fixed Android assert/action on an absent element wrongly reporting success:
  `execute_and_record` now gates on `element is not None`.

### Added
- `test_public_surface.py` — pins the CLI package's public symbols.
- Per-platform locator matrix in `--capabilities` (`locators` / `features`);
  ref/bbox/screenshot-annotation/visual-fallback reported as Web-only.
- `--web-stop` — terminate the persistent Chromium (CDP port 9333); idempotent.
- `doctor` web preflight check: reads `report/web_session.json` and surfaces a
  leftover persistent Chromium as an advisory NOTE (never fails `--doctor`).
- Live smoke tests against real hardware, opt-in and skipped by default:
  - `test_web_smoke_live.py` (`RUN_LIVE_WEB_SMOKE=1`)
  - `test_android_smoke_live.py` (`RUN_LIVE_ANDROID_SMOKE=1`)
  - `test_ios_smoke_live.py` (`RUN_LIVE_IOS_SMOKE=1`)

### Docs
- Corrected `capability-matrix.md` / `agent_guide.md`: ref/bbox/visual fallback
  are Web-only.
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
