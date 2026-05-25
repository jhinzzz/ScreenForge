# MCP Setup Guide

Connect ScreenForge to any MCP-compatible AI Agent in under 3 minutes.

## What You Get

Once connected, your AI Agent gains 5 tools:

| Tool | Description |
|------|-------------|
| `ui_agent_inspect_ui` | Get the current page's UI tree (DOM/XML) |
| `ui_agent_execute` | Execute a single UI action (click, input, etc.) |
| `ui_agent_capabilities` | List supported platforms, actions, and locators |
| `ui_agent_load_run` | Load a previous test run's results |
| `ui_agent_load_case_memory` | Load test case execution history |

## Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "screenforge": {
      "command": "screenforge",
      "args": ["--mcp-server", "--platform", "web"]
    }
  }
}
```

Config file location:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## Cursor

Add to your `.cursor/mcp.json` in the project root:

```json
{
  "mcpServers": {
    "screenforge": {
      "command": "screenforge",
      "args": ["--mcp-server", "--platform", "web"]
    }
  }
}
```

## Cline (VS Code)

Add to your Cline MCP settings:

```json
{
  "mcpServers": {
    "screenforge": {
      "command": "screenforge",
      "args": ["--mcp-server", "--platform", "web"]
    }
  }
}
```

## Claude Code

Add to your `.claude/settings.json`:

```json
{
  "mcpServers": {
    "screenforge": {
      "command": "screenforge",
      "args": ["--mcp-server", "--platform", "web"]
    }
  }
}
```

## Platform Options

Replace `--platform web` with your target:

| Platform | Flag | Requirements |
|----------|------|-------------|
| Web | `--platform web` | Chrome with `--remote-debugging-port=9222` |
| Android | `--platform android` | `adb devices` shows connected device |
| iOS | `--platform ios` | WebDriverAgent running on device |

## Verify It Works

After configuring, ask your Agent:

> "Use screenforge to inspect the current page"

You should see the Agent call `ui_agent_inspect_ui` and return a structured UI tree.

## Typical Agent Workflow

```
Agent thinks: "I need to test the login flow"
  │
  ├─ calls ui_agent_inspect_ui → gets DOM tree
  │
  ├─ analyzes DOM, finds email input
  │
  ├─ calls ui_agent_execute {action: "input", locator_type: "css", locator_value: "#email", extra_value: "test@example.com"}
  │
  ├─ calls ui_agent_inspect_ui → verifies input filled
  │
  └─ repeats until flow is complete
```

## Troubleshooting

Run `screenforge --doctor --platform web` to diagnose connection issues.

Common fixes:
- **"Playwright not installed"**: Run `pip install screenforge` or `playwright install chromium`
- **"CDP endpoint unreachable"**: Start Chrome with `google-chrome --remote-debugging-port=9222`
- **"OPENAI_API_KEY not set"**: Only needed for autonomous mode, not MCP inspect/execute
