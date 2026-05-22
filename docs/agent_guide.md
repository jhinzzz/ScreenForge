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

## Element Location Capabilities

- **Ref system (@N)**: `inspect_ui` assigns ref numbers (@1, @2...) to each interactive element. Use `--locator-type ref --locator-value @3` to locate directly.
- **Bbox coordinates**: Each element includes `x, y, w, h` bounding box for coordinate-based clicking or visual comparison.
- **Screenshot annotation**: In `--vision` mode, screenshots are automatically annotated with ref numbers for visual location.
- **Visual fallback (VLM)**: When DOM/XML cannot locate the target (Canvas, games, custom-rendered UI), the engine calls a VLM to parse coordinates from screenshots.

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
- **Exit code 1**: Failure — check terminal logs for error codes:
  - `[E020] UI stagnation`: Action executed but page didn't change. Add preconditions and retry.
  - `[E022] Circuit breaker`: Consecutive failures reached threshold. Narrow steps or add `--vision`.
  - `[E030] Ref not found`: Element ref is stale. Re-run `inspect_ui` to refresh.
- **Never blindly retry with the same parameters**

## Prohibited Actions

1. **Do NOT use `--goal`**: It calls an internal LLM to think for you — wastes tokens and produces worse results.
2. **Do NOT write UI code from imagination**: You cannot see the real screen. Always `inspect_ui` first to get the DOM tree.
3. **Do NOT pass raw natural language through**: You are responsible for understanding requirements. ScreenForge only executes actions.
