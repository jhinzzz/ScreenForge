# awesome-mcp-servers Submission

PR content for https://github.com/punkpeye/awesome-mcp-servers

---

## Entry to add

Under the **Testing** or **Browser Automation** category:

```markdown
- [ScreenForge](https://github.com/jhinzzz/ScreenForge) - Your AI agent runs the test, you keep the pytest file. Turns Agent interactions into self-healing, replayable pytest scripts — and drives real iOS + Android devices, not just Chrome (Playwright). Semantic cache, Allure reporting.
```

---

## PR Title

`Add ScreenForge - AI-driven UI test generation via MCP`

## PR Body

**What does this MCP server do?**

ScreenForge exposes 5 MCP tools that let any AI Agent drive UI automation across Web, Android, and iOS:

| Tool | Description |
|------|-------------|
| `ui_agent_inspect_ui` | Get the current page's UI tree (DOM/XML) |
| `ui_agent_execute` | Execute a single UI action (click, input, swipe, etc.) |
| `ui_agent_capabilities` | List supported platforms, actions, and locators |
| `ui_agent_load_run` | Load a previous test run's results |
| `ui_agent_load_case_memory` | Load test case execution history |

**What makes it different from existing entries?**

- **You keep the pytest file**: generates **replayable pytest scripts** that run in CI (not just one-shot browsing)
- **Real devices, not just browsers**: drives physical Android (uiautomator2) and iOS (wda) over the same MCP surface — the one thing pure-web agents (Playwright MCP, Browser Use) can't do
- **Self-healing engine** auto-repairs broken locators with confidence scoring + AST validation
- **No hidden LLM calls**: the Agent is the brain, ScreenForge is the hands

**Setup:**

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

**Links:**
- GitHub: https://github.com/jhinzzz/ScreenForge
- MCP setup guide: https://github.com/jhinzzz/ScreenForge/blob/main/docs/mcp-setup.md
- PyPI: `pip install screenforge`

---

## Checklist before submitting

- [ ] Verify which category fits best (check current repo structure)
- [ ] Ensure alphabetical ordering within the category
- [ ] Follow the existing entry format exactly
- [ ] Include only one sentence in the list entry
