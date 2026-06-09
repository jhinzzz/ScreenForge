# ScreenForge Capability Matrix

**[中文](./capability-matrix_CN.md)** | English

This document describes the capability boundaries that are currently shipped and verified in this repository. If an upper-layer Agent needs a machine-readable version, run `python agent_cli.py --capabilities` directly; for a machine-readable execution entry point, use `--tool-request`, `--tool-stdin`, or `--mcp-server`.

## Platform Support Overview

| Platform | Connection | Page-structure capture | Screenshot | Physical action execution | Video/state artifacts | Current maturity |
|---|---|---|---|---|---|---|
| Android | `uiautomator2` | XML compression | Supported | Supported | `scrcpy` recording | High |
| iOS | `facebook-wda` | XML compression (inline-label de-shadow) | Supported | Basic support | No native recording yet | Low |
| Web | Playwright + CDP | DOM compression (pierces open shadow DOM + same-origin iframes) | Supported | Supported | Playwright video + storage state | Medium |

> ℹ️ **Web DOM compressor pierce capability (2026-06)**: `compress_web_dom` recursively walks open shadow
> DOM and same-origin/`srcdoc` iframes; an iframe-child element's bbox is offset back to top-document
> coordinates by the iframe's position + border + padding, guaranteeing ref/coordinate clicks don't
> land off-target. **Non-interactive judgment** (all still recorded for assertions, but marked
> `clickable:false` to keep the LLM from clicking dead elements and hanging on timeouts):
> - `disabled` / `aria-disabled` controls → `disabled:true`; judged via the `:disabled` pseudo-class,
>   so `<fieldset disabled>` propagating to descendant controls (including the first-`<legend>` exemption and nested inheritance) is also covered.
> - `inert` subtree (the standard pattern of marking the backdrop inert when a `<dialog>` is open) → a separate `inert:true` field
>   (**not** treated as `disabled` — the two are semantically distinct), and the inert state is inherited across shadow / same-origin iframe boundaries.
>
> **Un-pierceable**: closed shadow roots, cross-origin iframes (browser security boundary, skipped silently).
>
> **Virtualized lists (react-window / virtualized tables) only see the viewport**: such components only render the in-viewport rows into the DOM;
> off-viewport rows simply don't exist, so the compressor can't see them and shouldn't fabricate them. This is an inherent limit, not a defect — use workflow B's
> `action scroll → re-inspect_ui` loop to get new rows (pinned by a live test: after scrolling, a re-inspect
> picks up the new slice and the old rows are no longer reported). Don't try to force-render every row (the token count would blow up).

> **Duplicate-named control disambiguation (`scope` / `dup_index`)**: when multiple clickable controls share the same (role, name)
> (e.g. one "Delete" per list row), the compressor adds two fields to these **ambiguous** elements: `scope` (the
> unique identifying leaf text of the row, e.g. "Bob Jones") and `dup_index` (DOM order). Non-ambiguous elements get neither (0 extra tokens).
> codegen uses `scope` to generate a scoped locator `get_by_text('Bob Jones', exact=True).locator('..').get_by_role('button', name='Delete')`
> — **no `.first`**, with strict-mode as the backstop: if the locator isn't unique it errors, never silently clicking the first row. `scope` passes
> an in-group uniqueness check (not adopted if shared by multiple rows or empty) + exact match (to avoid "Bob" matching "Bob Jones").
> When disambiguation truly fails (same-name rows with identical identifiers / too long / no row identifier) → only `dup_index` is kept, and codegen takes the honest
> `pytest.skip`, never writing `.first` (the lie of clicking the first row) or `.nth(k)` (positional, coordinate-style brittleness).

> ℹ️ **Unified disabled schema (consistent across all three platforms, 2026-06)**: disabled / non-interactive controls are reported by all three platforms' compressors with
> **the same `disabled: true` field** (Web `:disabled`/`aria-disabled`, Android `enabled="false"`,
> iOS WDA `enabled="false"`), and all **still record** the control (so existence/disabled state stays assertable) but without a `clickable` mark, to keep the
> LLM from clicking dead controls and hanging on timeouts. Early iOS once used the opposite `enabled:false` key, now unified to `disabled:true`, so the single
> LLM brain only needs to recognize one "can't interact" vocabulary across platforms. Android real-device verified: the empty SIM slot on the data-roaming page (naturally disabled) is correctly
> marked `disabled` and unclickable.

> ℹ️ **iOS list-row label de-shadow (Cell/Button/Switch, 2026-06)**: iOS (WDA) hangs each list row's label
> **simultaneously** on the row's inline interactive control (`Button`/`Cell`/`Switch`) and a nested `StaticText`, so flat compression
> makes the same label repeat 2-3 times per row — one tappable target + one meaningless text shadow (a Switch row is even a `Cell` +
> `StaticText` + `Switch` triple). Measured on a real device (iOS 18.3 / Settings): of the 44 elements on the keyboard screen, 14 (32%) are pure
> text shadows; about half the rows on the home screen are like this. Beyond wasting tokens, it makes `d(label='通用')` ambiguous (matching both the tap target
> and its text shadow). The compressor now collapses each row to **the single actionable control unique to that label** (priority `Switch > Button >
> Cell`), discarding the StaticText shadow. **Honesty boundaries (all verified on-device)**: de-shadow is **visibility-aware** — it never lets an invisible
> higher-priority twin erase its visible sibling (a real on-screen element must never vanish); **exact same-label** match only (a distinct subtitle,
> e.g. the title/subtitle on the Apple-account row, survives); scoped within the row, **not crossing a nested `Cell` boundary** (an inner row's distinct label
> isn't eaten by the outer wrapper); a standalone caption with no interactive twin (e.g. `关`/Off) survives; a `Switch` keeps its on/off `value`.
> Real-device before/after: the Settings home goes 31 → 20 elements, the keyboard screen 44 → 21, with every targetable row preserved.

> ℹ️ **Android list-row label promotion (RecyclerView / Preference, 2026-06)**: the dominant shape of an Android list row is a
> **clickable container** (LinearLayout/ViewGroup, no own text/desc) + the label in a **non-clickable child TextView**.
> Flat compression splits a row into two elements — an unlocatable headless clickable block (no text/desc/id) + a text node marked
> `clickable:false`, so that **no element is both clickable and labeled**: the LLM brain, told by the P4 contract that the only
> labeled thing (e.g. "应用") isn't clickable, avoids it; external agents see a pile of unlocatable clickable blocks. Measured on a real device (Settings
> home): 16 of 18 clickable elements are unlocatable. The compressor now promotes each row's **title** (or first surviving) label child to
> `clickable:true` — a real node with a real id; tapping it bubbles to the clickable ancestor (real-device verified) — and suppresses the redundant empty container.
> **Zero coordinates. Honesty boundaries**: a disabled row isn't promoted; an icon-only container (no label) or one whose only labels would be dropped by the id/desc filters
> stays an honest headless clickable block rather than vanishing; nested cards each promote their own label, and an outer wrapper doesn't steal an inner label
> (an outer wrapper around an already-promoted inner card stays a clickable block without a locator — a known honesty limit). Real-device before/after:
> 18 clickable / 0 labeled-clickable / 16 unlocatable → 20 / 19 / 0.

## Element Location Capability

> ⚠️ **ref / bbox / screenshot annotation / visual fallback are Web-only.** The mobile UI-tree compressors
> (`utils_xml.py` / `utils_ios.py`) don't produce ref numbers or bbox coordinates, and the visual fallback in
> `executor.py` only takes effect for `platform == "web"`. For the machine-readable version see the
> `locators` / `features` fields of `python agent_cli.py --capabilities`.

| Capability | Android | iOS | Web | Notes |
|---|---|---|---|---|
| ref number (@N) | Not supported | Not supported | Supported | Only `compress_web_dom` assigns a ref to each Web element; mobile produces none |
| bbox coordinates (x,y,w,h) | Not supported | Not supported | Supported | Only Web elements carry bounding-box coordinates, used for coordinate clicks or visual comparison |
| Screenshot annotation | Not supported | Not supported | Supported | Under `--vision` mode, only Web auto-generates a screenshot annotated with ref numbers |
| Visual fallback (VLM) | Not supported | Not supported | Supported | Web only: when the DOM can't locate, calls the VLM to parse coordinates from the screenshot (the gate in `executor.py` is on web) |
| css selector | N/A | N/A | Supported | Preferred locator on Web |
| resourceId | Supported | Mapped to name | N/A | Android native resource-id; iOS maps to `name` |
| text / description | Supported | Supported (mapped to label) | Supported | Cross-platform, located by visible text or accessibility description |

## CLI Mode Support

| Mode | Android | iOS | Web | Notes |
|---|---|---|---|---|
| `run` | Supported | Basic support | Supported | Autonomously explores by default and generates a pytest script |
| `action` | Supported | Basic support | Supported | Single-step immediate action execution |
| `workflow` | Supported | Basic support | Supported | Semi-structured YAML workflow execution |
| `doctor` | Supported | Supported | Supported | Only checks the environment and preconditions |
| `plan-only` | Supported | Basic support | Supported | Generates a pre-execution plan, doesn't execute physical actions |
| `dry-run` | Supported | Basic support | Supported | Runs the decision chain and outputs would-execute results, doesn't execute physical actions |
| `resume-run-id` | Supported | Supported | Supported | Recovers minimal context from an existing run report |
| `mcp-server` | Supported | Supported | Supported | Exposes a minimal MCP tools interface over stdio |

## Playground Live Mirror (2026-06)

`screenforge --playground` starts a long-lived local visualization process (FastAPI, default `:7860`). After enabling the execution-side
`--playground-sink` (**off by default, opt-in**), the short-lived execution process best-effort pushes the **generated pytest code + screenshot**
to the playground every step, and the browser links three panes in real time: **screenshot ｜ read-only code pane (Prism syntax highlight + latest-line highlight) ｜ action history**,
with a filmstrip timeline at the bottom (click any frame to time-travel).

| Entry | Hooks the sink | step_index source | Screenshot cadence |
|---|---|---|---|
| `--action` (single step) | Supported | session count under `--session-id` (one session = one timeline); a bare single step is fixed at 1 | one frame per step |
| `workflow` YAML (multi-step) | Supported | loop counter (single process, multi-step, naturally continuous — the main battlefield) | one frame per step |
| `main.py` (human recording) | Supported | history step count incremented (benchmarked against Cypress Studio) | one frame per step |

> ℹ️ **Architecture (path A: HTTP Sink)**: the short-lived CLI process and the long-lived playground have **no shared memory**
> (the `_SharedAdapterManager` name is misleading — it doesn't actually span processes), so the only viable real-time channel is network IPC. The sink hangs
> **after** `save_to_disk` and is a pure **bypass observer**: it reuses each step's already-produced `result["code_lines"]` and the three-platform-unified
> `take_screenshot() -> bytes` (a `base_adapter.py` abstract method), changing neither the execution flow, nor codegen, nor disk writes.
>
> **Red line (exit-code contract)**: the sink is fire-and-forget throughout — daemon-thread push + detached timeout `(0.2, 0.25)` (the single-step `--action` has an additional `_JOIN_TIMEOUT=0.3` finalization cap),
> and if the playground isn't open / refuses the connection / hangs, it's **silently skipped** (`log.debug`). It must **never** let a failed push affect `--action`'s
> `0/1` exit code or runtime (when off, it doesn't even call `take_screenshot` — zero overhead). If screenshot capture itself throws → skip that frame's
> screenshot but still push the code (degrade-don't-crash).
>
> **Mobile "real-time" is step-by-step (an honesty boundary, not a defect)**: android `dump_hierarchy`+`take_screenshot`, iOS WDA
> screenshots run ~0.5–2s per step — the device's physical ceiling. The frontend faithfully renders discrete snapshots, not pretending to be a continuous video stream. Web additionally has a CDP screencast
> of continuous frames as an "inter-action preview" overlay (kept, not removed), but the primary screenshot events are aligned with code steps via `take_screenshot` discrete snapshots.
>
> **Multi-run isolation + bounded memory (arch#2)**: the playground accumulates step metadata namespaced by `run_id`, with an `OrderedDict`
> LRU (≤20 runs × ≤500 steps/run, evicting the oldest / truncating the head when over the limit). **base64 frames don't enter the accumulation log** — only the single-slot live frame +
> SSE broadcast; historical frames are read from the reporter's already-persisted `screenshots/step_NNN.png`, so a playground restart loses nothing.
>
> **Time-travel (single-session rewind) is shipped**: data persistently accumulates by `step_index`, backed by a read-only `GET /api/run/{run_id}/steps`
> endpoint, and clicking any filmstrip frame / history step rewinds the large screenshot to that step while the code pane highlights the matching line (screenshot / code / history all cross-linked) — all **within the current run**. What's left for a future standalone iteration is **cross-session persisted-frame replay** (paging back through old runs after the page is closed). The code pane is **read-only** this round (editable write-back conflicts with codegen's automatic disk writes — not this round).

### Brain's Eye View (DOM tree)

A read-only, live, hierarchical panel showing the **filtered element set the AI brain actually perceives at each step, re-hung into its real parent/child structure** — not the browser's raw DevTools DOM.

- **Sidecar capture** (`playground/dom_capture.py`): reuses the LLM compressors' survival/filter predicates but preserves hierarchy. Never touches `compress_web_dom` / `compress_android_xml` — the flatten-for-token-economy path is untouched. Web: a hierarchical `page.evaluate` walk emitting `ref` `@N` + bbox `x/y/w/h`. Mobile (Android/iOS): parses raw `dump_hierarchy()` / `source()` XML preserving nesting (no `ref`, no bbox — honest, not faked).
- **Opt-in / zero cost**: capture rides the existing `--playground-sink` observer path (OFF by default = zero added cost; not even attempted when the sink is off).
- **Red line preserved**: the tree push is a separate fire-and-forget `POST /api/dom`, decoupled from the step push and never join-waited, so it can never delay or change `--action`'s `0/1` exit code.
- **Disk-backed store**: trees (25–80 KB each) are persisted to disk by the resident server, keyed by the cross-process-stable `run_key` (not `reporter.run_id`, which differs per `--action` process). In-memory index holds only `run_key → {step indices}`; LRU ≤ 5 run dirs.
- **On-demand fetch, zero SSE overhead**: the SSE `step` event carries only a `has_dom_tree` boolean; the frontend fetches a step's tree via `GET /api/run/{run_id}/step/{step_index}/dom` only when the drawer is open and the step is in view. 404 = no tree for this step (quiet). Most users never open the panel ⇒ zero tree traffic on SSE.
- **Web**: `ref` badge + ember-highlighted target row + ember bbox overlay on screenshot; hover → blue bbox.
- **Mobile honest degrade**: no `ref` badge, no bbox overlay (absent, not faked); hover rail turns amber; one-time dismissable notice. The tree is genuinely hierarchical (a real improvement over the flat LLM output).
- **Read-only**: no editing, no delete-step, no act-on-element. UX: collapsible right-edge drawer (pinnable; hotkey `B`); full ARIA keyboard nav (↑/↓/←/→/Home/End, `/` to search); copy-locator; `+N −N ~N` per-step diff badge; keyed reconciler preserves expand/scroll state across steps.

## Human Entry vs Agent Entry Division of Labor

| Entry | Audience | Natural-language direct driving allowed | Internal third-party LLM reasoning allowed | Recommended use |
|---|---|---|---|---|
| `main.py` | Humans | Allowed | Allowed | Natural-language debugging, interactive recording |
| `agent_cli.py --action/--workflow` | Agent / dev | Not recommended | Not needed | Structured execution, troubleshooting, code generation |
| `--tool-request` / `--tool-stdin` / `--mcp-server` | Agent | Not allowed | Not allowed | `inspect_ui -> load_case_memory -> execute` |

> `agent_cli.py` is a 6-line shim; all logic is implemented inside the `cli/` package.

## Shipped Action Types

| Action | Android | iOS | Web | Notes |
|---|---|---|---|---|
| `click` | Supported | Basic support | Supported | Standard click |
| `long_click` | Supported | Basic support | Simulated via delayed click | |
| `hover` | Ignored | Ignored | Supported | Only truly takes effect on Web |
| `input` | Supported | Basic support | Supported | |
| `swipe` | Supported | Depends on underlying capability | Supported | Web simulates via the scroll wheel |
| `press` | Supported | Basic support | Supported | |
| `scroll_into_view` | N/A | N/A | Supported | Web only: element-level scroll into the viewport (better than a blind swipe). Mobile has no robust coordinate-free equivalent |
| `select` | N/A | N/A | Supported | Web only: native `<select>` option selection. `extra_value` = option text or value |
| `upload` | N/A | N/A | Supported | Web only: file `<input>` upload. `extra_value` = file path |
| `double_click` | N/A | N/A | Supported | Web only: double click |
| `right_click` | N/A | N/A | Supported | Web only: right click (triggers the context menu) |
| `drag` | N/A | N/A | Supported | Web only: drag. locator locates the source, `extra_value` = target (css or text). Pointer-style drag; HTML5 dataTransfer native DnD is out of scope |
| `wait_for` | Supported | Basic support | Supported | Explicit synchronization: wait for an element to appear/disappear, replacing dead waits. `extra_value` = `visible` (default)/`hidden` |
| `assert_exist` | Supported | Basic support | Supported | Element appears (Web auto-polls via `wait_for(visible)`) |
| `assert_not_exist` | Supported | Basic support | Supported | Element gone/absent (Web `to_be_hidden`, Android `wait_gone`) |
| `assert_text_equals` | Supported | Basic support | Supported | Text exactly equal (Web auto-retries via `expect().to_have_text`) |
| `assert_text_contains` | Supported | Basic support | Supported | Text contains substring (preferred for dynamic text, Web `expect().to_contain_text`) |
| `assert_value` | Supported | Basic support | Supported | Form-field value (Web `expect().to_have_value`, mobile reads text) |
| `assert_url` | N/A | N/A | Supported | Web only: page URL contains substring (a global action, auto-retries via `expect().to_have_url`) |

> ℹ️ **Web assertions use Playwright `expect()` auto-retry**: the generated test code uses `expect(locator).to_*(..., timeout=...)` for text/value/visibility assertions, polling until the condition is met or it times out, eliminating the "read once then compare" flakiness on async UIs. The `execute()` real-time verdict path keeps bounded polling and returns a boolean, letting the autonomous loop and `--json` distinguish "assertion failure" from "engine error". `goto/press/swipe` generated code no longer writes a fixed `wait_for_timeout` dead wait — `goto` synchronizes via `wait_until='load'`, and subsequent actions rely on the locator's own auto-wait.

> ℹ️ **Failure-feedback ergonomics (2026-06)**: when `--action --json` fails, an engine_error (not an assertion failure)
> returns a structured diagnosis: `error_code` + `fix` (the same source as the stderr `[E0xx]`, see `common/error_codes.py`),
> did-you-mean `candidates` (`difflib` ranks page elements by text/desc/name similarity, passing the 0.55 threshold,
> each candidate containing `{text, score, locator}`, where `locator` can be retried directly), `recommended_next_step`, and
> the **current `ui_tree`** (the agent doesn't need to send another `inspect_ui`). **Honesty boundaries**: all similarities below the threshold → empty
> `candidates` + a re-inspect suggestion, never fabricating; a broken connection that can't capture the page → `ui_tree` degrades to empty and
> `candidates` follows suit as empty (the payload shape is unchanged, no fabricated elements); `assertion_failed:true`
> is a verdict, not a location problem → no candidates attached, no retry suggestion. The success payload and `inspect_ui` add `current_url`
> (web only; mobile has no URL concept and honestly returns ""). The MCP `execute` exit is a minimal enhancement (`failure_diagnosis`
> = `{error_code, message, fix}`, no candidates — the run-report shape has no live ui_elements; and it only takes effect once the run report passes the
> executor's error_code through into the summary, which is currently an honest empty object).

## Self-Heal Engine

| Capability | Status | Notes |
|---|---|---|
| Structured JSON output | Shipped | `HealResult` dataclass, returns `confidence / fix_description / fixed_code` |
| 4-strategy JSON parsing | Shipped | direct JSON → JSON fence → balanced-bracket extraction → markdown code block → raw-text fallback |
| AST syntax validation | Shipped | validated by `ast.parse(fixed_code)`; a syntax error sets confidence=0.0 |
| Confidence threshold | Shipped | skips the self-heal when below `AUTO_HEAL_MIN_CONFIDENCE` (default 0.7) |
| Pre-overwrite backup | Shipped | generates a `.bak` file via `shutil.copy2` before overwriting the test script |

## Currently Known Boundaries

1. `APP_ENV_CONFIG` in this repository currently only configures the `dev` environment by default; other environments must be supplied by the user.
2. iOS already has structure capture (WDA XML compression + inline-label de-shadow), but recording and launch flows are still weaker than Android / Web, so overall maturity is on the low side.
3. Web currently depends on an already-launched Chrome CDP session; `WEB_CDP_URL` must be ready before use.
4. `plan-only` and `dry-run` are control-plane capabilities focused on preview and troubleshooting; they don't replace the formal `run` mode.
5. `mcp-server` currently exposes five tools: `ui_agent_capabilities`, `ui_agent_inspect_ui`, `ui_agent_load_case_memory`, `ui_agent_execute`, and `ui_agent_load_run`.
6. Visual fallback (VLM) depends on the `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL_NAME` config; when unconfigured it automatically degrades to pure DOM/XML location.
7. After a real `run` execution finishes, it automatically updates `memory/case_memory.json` for subsequent Agent runs to reuse test assets.
8. The Playground Live Mirror depends on the `screenforge[playground]` extra (`fastapi`/`uvicorn`/`websockets`). `--playground-sink` is off by default — zero overhead for pure CI/agent test runs; enable it only when you need to "watch as you write". Single-session time-travel rewind is shipped; cross-session persisted-frame replay is not yet shipped.
9. The Brain's Eye View DOM tree panel is **single-session and read-only**: it shows the current session's live tree and allows only expand/collapse/search/copy-locator interactions. Reverse spatial lookup (click a screenshot coordinate → highlight the corresponding node) and SSE diff-streaming of tree deltas are deferred to a future iteration.
