# ScreenForge

[![CI](https://github.com/jhinzzz/ScreenForge/actions/workflows/ci.yml/badge.svg)](https://github.com/jhinzzz/ScreenForge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/jhinzzz/ScreenForge/blob/main/LICENSE)

**[中文](https://github.com/jhinzzz/ScreenForge/blob/main/README_CN.md)** | English

> Describe what to test. Watch it happen. Get a pytest script.

ScreenForge is an AI-driven UI automation engine that turns natural language into executable test scripts. Unlike record-and-replay tools, you don't perform the actions yourself — the AI does it for you.

![ScreenForge Demo](https://raw.githubusercontent.com/jhinzzz/ScreenForge/main/docs/assets/demo.gif)

## Why ScreenForge?

| | Playwright Codegen | Browser Use | Midscene.js | **ScreenForge** |
|---|---|---|---|---|
| Need to perform actions yourself? | Yes | No | No | **No** |
| Generates replayable test scripts? | Yes | No | No | **Yes (pytest)** |
| Self-healing when UI changes? | No | No | No | **Yes** |
| Works as AI Agent tool (MCP)? | No | Yes | No | **Yes** |

**Core architecture**: Your AI Agent is the brain (understands requirements, makes decisions). ScreenForge is the hands (executes UI actions, generates code).

## Quick Start

```bash
pip install screenforge

# See the magic without any API key:
screenforge --demo

# For real usage, set your LLM key:
export OPENAI_API_KEY=sk-...

# Inspect the current page (returns DOM tree for your Agent to analyze):
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin

# Execute a single action:
screenforge --action click --platform web --locator-type text --locator-value "Login"
```

## How It Works

```
You (or your AI Agent)          ScreenForge
        │                            │
        ├──── "Test the login" ─────►│
        │                            ├── inspect_ui (get DOM tree)
        │◄── DOM tree ──────────────┤
        │                            │
        ├──── click #email ─────────►│
        ├──── input "user@..." ─────►│
        ├──── click "Sign In" ──────►│
        │                            │
        │◄── pytest script ─────────┤
        │◄── Allure report ─────────┤
```

Each step: **inspect → decide → act → verify**. The AI decides, ScreenForge executes.

## Features

- **Cross-platform**: Android (uiautomator2), iOS (wda), Web (Playwright)
- **Self-healing engine**: When tests break due to UI changes, the engine auto-repairs locators with confidence scoring and AST validation
- **L1/L2 semantic cache**: Same page + same instruction = instant response, no LLM call needed
- **Visual fallback**: When DOM can't locate elements (Canvas, games), VLM parses screenshots
- **MCP server**: Any MCP-compatible Agent can drive ScreenForge natively
- **Structured output**: JSON Lines events + `report/runs/<id>/` artifacts for CI integration
- **Live Mirror playground**: Watch the generated pytest code grow line-by-line beside a live screenshot as the test runs — `screenforge --playground`. See the [Playground Guide](https://github.com/jhinzzz/ScreenForge/blob/main/docs/playground-guide.md)

## Agent Integration (Claude Code / Cursor / Codex)

ScreenForge exposes itself as a tool for AI Agents. The standard loop:

```bash
# 1. Get page structure (your Agent analyzes it)
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin

# 2. Your Agent decides what to do, sends precise actions
screenforge --action click --platform web --locator-type text --locator-value "Login"

# 3. Verify the result, repeat
echo '{"operation":"inspect_ui","platform":"web"}' | screenforge --tool-stdin
```

For batch operations, use workflows:

```bash
screenforge --workflow ./workflows/login.yaml --platform web --json
```

Or start the MCP server for native Agent integration:

```bash
screenforge --mcp-server
```

## GitHub Actions

Add ScreenForge to your CI pipeline:

```yaml
- uses: jhinzzz/ScreenForge@v1
  with:
    platform: web
    workflow: ./workflows/login.yaml
    openai-api-key: ${{ secrets.OPENAI_API_KEY }}
```

Results are auto-uploaded as Allure artifacts. See [action.yml](https://github.com/jhinzzz/ScreenForge/blob/main/action.yml) for all inputs.

See [Agent Integration Guide](https://github.com/jhinzzz/ScreenForge/blob/main/docs/agent_guide.md) for the complete protocol.

## Installation (from source)

```bash
git clone https://github.com/jhinzzz/ScreenForge.git
cd ScreenForge
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

Platform-specific extras:
- Web only: `pip install -e .` (default, includes Playwright)
- Android: `pip install -e ".[android]"`
- iOS: `pip install -e ".[ios]"`
- ML/cache: `pip install -e ".[ml]"` (sentence-transformers for semantic cache)

## Configuration

```bash
# Required: LLM API key (OpenAI-compatible endpoint)
export OPENAI_API_KEY=sk-...

# Optional: custom endpoint (defaults to api.openai.com)
export OPENAI_BASE_URL=https://api.openai.com/v1

# Optional: model (defaults to gpt-4o)
export MODEL_NAME=gpt-4o
```

Or create a `.env` file (copy from `.env_template`).

## Badge

If ScreenForge generates tests for your project, add this badge to your README:

```markdown
[![Tests by ScreenForge](https://img.shields.io/badge/tests%20by-ScreenForge-blue?logo=pytest)](https://github.com/jhinzzz/ScreenForge)
```

[![Tests by ScreenForge](https://img.shields.io/badge/tests%20by-ScreenForge-blue?logo=pytest)](https://github.com/jhinzzz/ScreenForge)

## Learn More

| Resource | Description |
|----------|-------------|
| [Mobile Setup](https://github.com/jhinzzz/ScreenForge/blob/main/docs/mobile-setup.md) | Android & iOS device connection guide |
| [MCP Setup (3 min)](https://github.com/jhinzzz/ScreenForge/blob/main/docs/mcp-setup.md) | Connect to Claude Desktop / Cursor / Cline / Claude Code |
| [Agent Guide](https://github.com/jhinzzz/ScreenForge/blob/main/docs/agent_guide.md) | Integration protocol for AI Agents |
| [Capability Matrix](https://github.com/jhinzzz/ScreenForge/blob/main/docs/capability-matrix.md) | Supported platforms, actions, and locators |
| [Playground Guide](https://github.com/jhinzzz/ScreenForge/blob/main/docs/playground-guide.md) | Live Mirror — watch code + screenshots grow as the test runs |
| [Workflow Examples](https://github.com/jhinzzz/ScreenForge/tree/main/docs/workflows) | YAML workflow templates |
| [CHANGELOG](https://github.com/jhinzzz/ScreenForge/blob/main/CHANGELOG.md) | Version history |

## Contributing

See [CONTRIBUTING.md](https://github.com/jhinzzz/ScreenForge/blob/main/CONTRIBUTING.md) for guidelines. Issues and PRs welcome!

## License

[MIT](https://github.com/jhinzzz/ScreenForge/blob/main/LICENSE)
