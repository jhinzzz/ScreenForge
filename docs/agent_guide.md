# ScreenForge Agent Integration Guide

You are the upstream Agent (Claude Code / Cursor / Codex). ScreenForge is your UI execution engine.

**You understand requirements, analyze the UI tree, and decide strategy. ScreenForge connects to devices, captures page structure, executes physical actions, and generates code.**

## Architecture Overview

```
agent_cli.py          # Compatibility entry (6-line shim), delegates to cli/dispatch.py
cli/                  # Real dispatch layer: parser / shared / reporter / doctor / modes/
  dispatch.py         # CLI entry main(), routes by execution mode
  modes/default.py    # --goal autonomous exploration loop (NOT recommended for Agents)
  modes/action.py     # --action single-step execution
  modes/workflow.py   # --workflow structured execution
  tool_protocol_handlers.py  # --tool-stdin / --tool-request / --mcp-server
```

`agent_cli.py` still works, but it's just a thin shell over `from cli.dispatch import main`. All logic lives in the `cli/` package.

## Day 1 Critical Path (4 Steps)

### 1. Get current page structure

```bash
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin
```

Returns a cleaned DOM/XML tree (Web returns JSON, Android returns compressed XML). **You analyze this tree and locate target elements.**

### 2. Execute single-step actions

Based on your analysis of the UI tree, execute step by step:

```bash
screenforge --action goto --platform web --extra-value "https://example.com"
screenforge --action click --platform web --locator-type text --locator-value "Login"
screenforge --action input --platform web --locator-type css --locator-value "#username" --extra-value "admin"
screenforge --action press --platform web --extra-value "Enter"
screenforge --action assert_exist --platform web --locator-type text --locator-value "Dashboard"
```

### 3. Re-inspect after each step

```bash
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin
```

Observe whether the page changed, then decide the next step. On failure, analyze exit code and logs to adjust strategy.

### Optimized: Action + Inspect in One Call (`--json`)

Instead of separate action + inspect calls, combine them with `--json`:

```bash
screenforge --action click --platform ios --locator-type text --locator-value "Login" --json 2>/dev/null
```

Returns a single JSON line on stdout:
```json
{"ok": true, "action": "click:Login", "platform": "ios", "ui_tree": {"ui_elements": [...]}, "element_count": 49, "output_script": "test_cases/ios/test_auto_agent_xxx.py"}
```

On failure:
```json
{"ok": false, "action": "click:Login", "platform": "ios", "result": "engine_error", "assertion_failed": false, "error": "Action failed: click:Login"}
```

**Assertion failures are different from engine errors.** When an `assert_exist` /
`assert_text_equals` step fails, the element/text simply did not match — the SUT
did not meet the assertion. This is a *verification verdict*, not an engine bug:

```json
{"ok": false, "action": "assert_exist:Dashboard", "platform": "ios", "result": "assertion_failed", "assertion_failed": true, "error": "Assertion failed: assert_exist:Dashboard"}
```

Branch on `assertion_failed` / `result`:
- `assertion_failed: true` → the assertion did not hold. **Do NOT retry or add
  `--vision`** — surface it as a test failure (the page did not reach the
  expected state).
- `result: "engine_error"` (assertion_failed false) → a real failure (locator
  not found, action blocked, connection). Re-inspect and adjust strategy.

This halves the round-trips needed per step — execute and observe in one call.

### Multi-Step Sessions (`--session-id`)

Group multiple actions into one test file and one recording:

```bash
# First action — creates session, starts recording (iOS only)
screenforge --action click --platform ios --locator-type text --locator-value "Login" --session-id my_flow --json 2>/dev/null

# Subsequent actions — appends to same test file
screenforge --action input --platform ios --locator-type text --locator-value "Username" --extra-value "admin" --session-id my_flow --json 2>/dev/null

# End session — stops recording, outputs summary
screenforge --session-end my_flow
```

All steps share one output script (`test_cases/<platform>/test_session_<id>.py`). On iOS, screen recording runs continuously across all steps.

### 4. Verify the generated script

```bash
pytest test_cases/web/test_xxx.py
```

### Advanced: Batch execution with workflows

When you have multiple deterministic steps, write a YAML workflow and execute at once:

```bash
screenforge --workflow ./my_workflow.yaml --output "test_cases/test_login.py" --platform web
```

Combine with `--plan-only` (view plan only) or `--dry-run` (simulate without executing) for pre-checks.

## Supported Actions

| Action | Description | Requires locator | Requires extra_value |
|--------|-------------|:---:|:---:|
| `goto` | Navigate to URL (Web only) | No | URL |
| `click` | Click element | Yes | No |
| `long_click` | Long press element | Yes | No |
| `hover` | Hover (Web only) | Yes | No |
| `input` | Type text | Yes | Text content |
| `swipe` | Swipe screen | No | up/down/left/right |
| `press` | Simulate key press | No | Key name (Enter/Back) |
| `assert_exist` | Assert element exists | Yes | No |
| `assert_text_equals` | Assert text matches | Yes | Expected text |

`locator_type` priority: `css` > `resourceId` > `text` > `description`

> **`not_found` is autonomous-mode-only.** It is an internal signal the `--goal`
> LLM brain emits when the target is absent from the UI tree — it is NOT a real
> action and never appears in `--action --json` output. As the agent you don't
> issue or receive it; the equivalent signal on the `--action` path is an
> `ok:false` locate failure (`result: "engine_error"`). Re-inspect, scroll, or
> add `--vision`.

## Element Location Capabilities

> **Per-platform — read the machine-readable source.** `screenforge --capabilities`
> returns `locators` (which `locator_type` works per platform) and `features` (which
> location features are platform-gated). Don't assume a locator works everywhere.
>
> | locator_type | Web | Android | iOS |
> |---|:---:|:---:|:---:|
> | `css` | ✅ | — | — |
> | `ref` (@N) | ✅ | ❌ | ❌ |
> | `resourceId` | — | ✅ | ✅ (→ name) |
> | `text` | ✅ | ✅ | ✅ (→ label) |
> | `description` | ✅ | ✅ | ✅ (→ label) |

- **Ref system (@N) — Web only**: on Web, `inspect_ui` assigns ref numbers (@1, @2...) to each interactive element; use `--locator-type ref --locator-value @3`. Android/iOS UI trees do NOT carry ref numbers — use `resourceId` / `text` / `description` there.
- **Bbox coordinates — Web only**: Web elements include an `x, y, w, h` bounding box for coordinate clicking / visual comparison. Mobile compressors don't emit bbox.
- **Screenshot annotation — Web only**: In `--vision` mode, Web screenshots are annotated with ref numbers.
- **Visual fallback (VLM) — Web only**: when the DOM can't locate the target (Canvas, games, custom-rendered UI), the engine calls a VLM to parse coordinates. This fallback is gated to the Web platform.

## Tool Protocol Entries

Beyond direct shell calls, machine-readable protocols are supported:

| Entry | Usage |
|-------|-------|
| `--tool-stdin` | `echo '{"operation":"inspect_ui","platform":"web"}' \| screenforge --tool-stdin` |
| `--tool-request` | `screenforge --tool-request ./request.json` |
| `--mcp-server` | `screenforge --mcp-server` (stdio MCP server) |

Supported operations: `capabilities`, `inspect_ui`, `load_case_memory`, `execute`, `load_run`

## Troubleshooting

- **Exit code 0**: Success — script generated at the `--output` path
- **Exit code 1**: Failure — first check `result` / `assertion_failed` in `--json`,
  then terminal logs for error codes:
  - **Assertion failure** (`assertion_failed: true`): an `assert_*` step did not
    hold. This is an expected verification verdict, **not** an engine bug — report
    it as a test failure, do NOT retry or add `--vision`.
  - `[E020] UI stagnation`: Action executed but page didn't change. Add preconditions and retry.
  - `[E022] Circuit breaker`: Consecutive failures reached threshold. Narrow steps or add `--vision`.
  - `[E030] Ref not found`: Element ref is stale. Re-run `inspect_ui` to refresh.
- **Never blindly retry with the same parameters**

> Note: in `--goal` autonomous mode, a failing final assertion fails the whole
> run immediately (no retry). Assertions are verdicts, so they are not retried.

### Web: persistent browser lifecycle

Web runs launch a detached Chromium (CDP port 9333) and **keep it running** across
calls so cookies/login persist (the PID is tracked in `report/web_session.json`).
When you're done, stop it explicitly so it doesn't linger:

```bash
screenforge --web-stop   # terminates the persistent Chromium; idempotent (no-op if none)
```

## Prohibited Actions

1. **Do NOT use `--goal`**: It calls an internal LLM to think for you — wastes tokens and produces worse results.
2. **Do NOT write UI code from imagination**: You cannot see the real screen. Always `inspect_ui` first to get the DOM tree.
3. **Do NOT pass raw natural language through**: You are responsible for understanding requirements. ScreenForge only executes actions.
