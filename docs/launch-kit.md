# Launch Kit

Ready-to-post templates for announcing ScreenForge.

---

## Show HN (Hacker News)

**Title:** Show HN: ScreenForge – Describe what to test, AI does it, outputs a pytest script

**Body:**

Hi HN,

I built ScreenForge because I was tired of the gap between "AI can browse for me" and "I need a repeatable test suite." Tools like Browser Use let AI click around, and Playwright Codegen records what *you* do — but nothing turns AI-driven exploration into deterministic pytest scripts you can run in CI.

ScreenForge fills that gap:

1. Your AI Agent (Claude, GPT, etc.) calls `inspect_ui` to get the DOM tree
2. The Agent decides what to do, sends precise actions (`click #email`, `input "admin"`)
3. ScreenForge executes each action and generates a pytest script with Allure reporting
4. If the UI changes later, the self-healing engine auto-repairs locators (with confidence scoring + AST validation)

It works as an MCP server, so any MCP-compatible Agent can drive it natively. Also supports Android (uiautomator2) and iOS (WebDriverAgent) — same API surface.

Key design choice: your Agent is the brain, ScreenForge is the hands. No hidden LLM calls burning tokens behind your back — you control the reasoning loop.

- Demo: https://github.com/jhinzzz/ScreenForge (GIF in README)
- MCP setup (3 min): https://github.com/jhinzzz/ScreenForge/blob/main/docs/mcp-setup.md
- pip install screenforge

Tech: Python 3.11+, Playwright, Rich CLI, semantic cache (sentence-transformers), AST-validated code generation.

Would love feedback on the Agent integration protocol and the self-healing approach.

---

## Reddit (r/Python, r/testing, r/MachineLearning)

**Title:** I built an AI-driven UI test generator that outputs real pytest scripts (not just recordings)

**Body:**

Most UI automation tools fall into two camps:

- **Record-and-replay** (Playwright Codegen): You do the actions, it records. Breaks when UI changes.
- **AI browsers** (Browser Use): AI clicks around, but no replayable output.

ScreenForge combines both: AI does the clicking, you get a pytest script.

**How it works:**
- Your AI Agent calls `inspect_ui` → gets the DOM/XML tree
- Agent decides what to do → sends `click`, `input`, `swipe` commands
- ScreenForge executes + generates a pytest file with Allure reporting
- Self-healing engine auto-fixes broken locators when UI changes

**Works with:** Claude Desktop, Cursor, Cline, Claude Code (via MCP), or any tool that can pipe JSON.

**Cross-platform:** Web (Playwright), Android (uiautomator2), iOS (WDA) — same API.

GitHub: https://github.com/jhinzzz/ScreenForge

`pip install screenforge && screenforge --demo`

Happy to answer questions about the architecture!

---

## Twitter/X Thread

**Tweet 1 (hook):**

I built an open-source tool that lets AI Agents generate real pytest scripts from UI interactions.

Not record-and-replay. Not "AI browsing."

Your Agent thinks. ScreenForge executes. You get a test suite.

🧵 How it works:

**Tweet 2 (problem):**

The problem:
- Playwright Codegen: YOU do the clicking. Breaks on UI changes.
- Browser Use: AI clicks, but no replayable test output.
- Midscene: No self-healing, no script generation.

I wanted: AI explores → deterministic pytest scripts → CI-ready.

**Tweet 3 (solution):**

ScreenForge's design:

1. Agent calls inspect_ui → gets DOM tree
2. Agent decides → sends precise actions
3. ScreenForge executes + generates pytest
4. UI changes? Self-healing auto-repairs locators

Your Agent = brain. ScreenForge = hands.

**Tweet 4 (MCP):**

Works as an MCP server out of the box.

Claude Desktop, Cursor, Cline, Claude Code — 3-minute setup.

Cross-platform: Web + Android + iOS, same API.

**Tweet 5 (CTA):**

GitHub: https://github.com/jhinzzz/ScreenForge

```
pip install screenforge
screenforge --demo
```

Star it if you're tired of maintaining brittle E2E tests ⭐

---

## Posting Strategy

1. **HN**: Post weekday 9-11am ET. Engage in comments for the first 2 hours.
2. **Reddit**: r/Python (largest reach), r/testing (targeted), cross-post 1 day apart.
3. **Twitter**: Thread format, post when US/EU overlap (~2pm UTC). Quote-tweet with demo GIF.
4. **Dev.to**: Longer-form tutorial post (reuse HN body + add code examples).
