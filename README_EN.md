# ScreenForge

[中文](./README.md) | **English**

> Agentic UI Automation Framework
>
> Cross-platform agentic UI automation engine for UI exploration, self-healing, and test generation.

ScreenForge is a cross-platform UI automation engine focused on UI exploration, interactive recording, structured execution, and test script generation.

### Who are you? Start here

| You are... | Entry point | First command |
|------------|-------------|---------------|
| **Human developer**, want to debug interactively | `main.py` | `python main.py --platform android` |
| **AI Agent** (Claude Code / Cursor / Codex), want to drive UI | `agent_cli.py --action` / `--tool-stdin` | See Agent Quick Start below |

**Human path** preserves the natural-language + LLM/VLM interactive recording experience.
**Agent path**: the upstream Agent understands PRD/commands; ScreenForge only does structured execution: `inspect_ui -> action/workflow -> verify`.

## ✨ Key Features

🗣️ **Two operating modes**:

- **Interactive recording mode (`main.py`)**: control the device like a chat session, generate standard test code step by step, with L1/L2 semantic cache.
- **Agent execution mode (`agent_cli.py --action/--workflow`)**: the upstream Agent understands PRD/commands, then calls ScreenForge's structured capabilities. `agent_cli.py` is a 6-line shim; all logic lives in the `cli/` package.

🎯 **ref locator system**: `inspect_ui` assigns a ref number (@1, @2...) to every interactive element, with bbox coordinates (x, y, w, h). Upstream Agents can reference elements directly without guessing resource-ids or xpaths.

👁️ **Multimodal visual perception (`--vision`)**: beyond the XML cleanup pipeline, supports annotated screenshots (ref numbers overlaid on screenshots) and visual fallback (VLM). When DOM/XML cannot locate the target (Canvas, games, custom-rendered UI), the engine calls a VLM to parse coordinates from screenshots.

🛡️ **Structured self-heal engine**: `HealResult` returns `confidence / fix_description / fixed_code`, validated by `ast.parse`, filtered by confidence threshold (default 0.7), with automatic `.bak` backup before overwriting. Built-in UI stagnation detection and circuit breaking prevent token waste.

📦 **Unified cross-platform architecture**: the engine uses a clean adapter pattern so the same workflow can target:

- `Android` (`uiautomator2`)
- `iOS` (`facebook-wda`)
- `Web` (`Playwright`)

🎬 **End-to-end traceability and replay**: generated scripts include standardized `@allure.step` annotations, automatic screenshots on assertion failure, and support for automatic execution video recording and Allure artifact attachment through Scrcpy or native platform mechanisms.

⚡ **Aggressive token optimization**: the Android XML cleanup and dimensionality reduction pipeline strips system noise, isolated symbols, and oversized redundant nodes. In practice, token consumption can drop by more than 80%, improving both latency and cost.

🧾 **Structured run artifacts (`--json`)**: `agent_cli.py` can stream JSON Lines events to stdout and persist `summary.json`, `steps.jsonl`, `artifacts.json`, and screenshot indexes under `report/runs/<run_id>/`, making it easy for higher-level agents and orchestration systems to consume the run.

## 🛠️ Requirements and Installation

### 1. Prerequisites

- Python 3.10 or above, Python 3.11+ recommended
- An Android device or emulator with Developer Mode and USB debugging enabled, connected to your computer

### 2. Create a virtual environment

Using a virtual environment is strongly recommended:

```bash
# Create the virtual environment
python -m venv .venv

# Activate it
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate
```

### 3. Install Python dependencies

After activating the virtual environment, run this in the project root:

```bash
pip install -r requirement.txt
```

If you only want the core dependencies, you can install them manually:

```bash
pip install uiautomator2 openai pytest allure-pytest loguru filelock numpy sentence-transformers
```

*(Note: for iOS or Web support, install the additional `facebook-wda` or `playwright` dependencies yourself.)*

### 4. Initialize the Android device

Run the following command to push the `uiautomator2` daemon (ATX app) to the device:

```bash
python -m uiautomator2 init
```

*(Note: the first run may trigger installation prompts on the device. Approve all of them.)*

### 5. Install supporting tools (Allure and Scrcpy)

- **Allure CLI** for visual report generation
  - macOS: `brew install allure`
  - Windows: use Scoop (`scoop install allure`) or download it from GitHub Releases and configure your environment variables
- **Scrcpy** for video recording during playback
  - macOS: `brew install scrcpy`
  - Windows: download it from the official Scrcpy repository

## ⚙️ Configuration

Using environment variables is strongly recommended so you do not leak secrets in code. You can also inspect `config/config.py` directly:

```bash
# API key
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# Base URL, useful when using a proxy or third-party gateway
export OPENAI_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"

# Model name, ideally a strong reasoning model with multimodal support
export MODEL_NAME="doubao-seed-2.0-lite-260215"
```

**Multi-environment configuration**: the project supports `dev`, `prod`, `us_dev`, and `us_prod` app package or URL switching. See `APP_ENV_CONFIG` in `config/config.py`.

## 🚀 Core Workflow 1: Integrate with a Super Agent (Agentic Mode)

Expose ScreenForge as a Tool/Skill for external Agents (Claude Code, Cursor, Codex). Have the Agent read `docs/agent_guide.md` for the full integration guide.

**Agent Quick Start** (3 steps):

```bash
# 1. Get current page UI tree (Agent analyzes it, not ScreenForge)
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin

# 2. Agent analyzes the UI tree, then sends precise single-step actions
python agent_cli.py --action click --platform web --locator-type text --locator-value "Login"

# 3. inspect_ui again to confirm page change, loop until done
echo '{"operation":"inspect_ui","platform":"web"}' | python agent_cli.py --tool-stdin
```

**Batch execution** via workflow:

```bash
python agent_cli.py --workflow ./docs/workflows/login_failure.yaml \
                    --output "test_cases/test_login.py" \
                    --platform android --json
```

**MCP integration**:

```bash
python agent_cli.py --mcp-server
```

### Core CLI parameters

- `--action`: single-step action (`click`, `input`, `assert_exist`, etc.). **Recommended Agent entry point.**
- `--workflow`: YAML workflow for multi-step structured execution
- `--goal`: (legacy) autonomous exploration with internal LLM. **Not recommended for Agent integration.**
- `--platform`: target platform (`android` | `ios` | `web`)
- `--vision`: enable multimodal visual assistance (annotated screenshots + VLM fallback)
- `--json`: stream JSON Lines events to stdout
- `--output`: output path for generated script
- `--tool-stdin` / `--tool-request` / `--mcp-server`: machine-readable protocol entries

Exit code `0` = success, `1` = failure or circuit breaker triggered.

### Run artifacts

- `report/runs/<run_id>/summary.json`: run summary, exit code, output script path
- `report/runs/<run_id>/steps.jsonl`: persisted structured event stream
- `report/runs/<run_id>/artifacts.json`: generated script, screenshots, and other artifact indexes
- `report/runs/<run_id>/screenshots/`: screenshots captured in `--vision` mode
- `memory/case_memory.json`: cross-run test memory for reuse

### Recommended docs for integrators

- `docs/agent_guide.md`: Agent integration guide (Day 1 critical path)
- `docs/capability-matrix.md`: platform/action/locator support matrix

## 💻 Core Workflow 2: Interactive Recording Mode

If you want to guide the recording process manually, step by step, launch the interactive engine:

```bash
python main.py
```

The terminal will then prompt you for natural-language commands:

```text
👉 Enter a natural-language command (type 'q' to quit): Click the "Profile" tab
[System] Fetching and compressing the XML tree...
[Action] Waiting for and clicking: text='Profile'

👉 Enter a natural-language command (type 'q' to quit): Verify that "Log Out" appears on the page
[Assert] Checking element existence: text='Log Out'
[Assert] ✅ Assertion passed

👉 Enter a natural-language command (type 'q' to quit): q
🎉 Recording finished!
```

In this mode, the framework enables the local **L1/L2 semantic cache (`CacheManager`)** by default. Similar UI trees and instructions can be resolved quickly without repeating LLM API calls. It also supports `u` (`Undo`) to revert the previous step.

### Interactive mode shortcuts

- `q`, `quit`, `exit`: quit recording and save the generated test script
- `u`, `undo`: revert the previous step
- `v-on`: enable vision mode
- `v-off`: disable vision mode

## 📁 Project Structure

```text
screenforge/
├── agent_cli.py             # Compatibility entry (6-line shim, delegates to cli/dispatch.py)
├── main.py                  # Interactive recording entry point
├── conftest.py              # Pytest fixtures, cross-platform dispatch, video/screenshot attachments
├── pytest.ini               # Pytest configuration
├── cli/                     # CLI dispatch layer (split from agent_cli.py in P1-2)
│   ├── dispatch.py          # CLI entry main(), routes by execution mode
│   ├── parser.py            # build_parser, validate_cli_args
│   ├── shared.py            # Lazy proxies, adapter connection, UI state capture
│   ├── reporter.py          # Reporter helpers
│   ├── doctor.py            # Environment diagnostics
│   ├── tool_protocol_handlers.py  # --tool-stdin / --tool-request / --mcp-server
│   └── modes/               # Execution modes
│       ├── default.py       # --goal autonomous exploration loop
│       ├── action.py        # --action single-step execution
│       ├── workflow.py      # --workflow structured execution
│       ├── plan.py          # --plan-only
│       └── dry_run.py       # --dry-run
├── config/
│   └── config.py            # Global config (API keys, timeouts, self-heal thresholds)
├── common/
│   ├── ai.py                # Base AI interaction layer (single-step parsing and cache)
│   ├── ai_autonomous.py     # Autonomous reasoning brain (self-healing, multimodal, memory)
│   ├── ai_heal.py           # Structured self-heal engine (HealResult, AST validation)
│   ├── executor.py          # Action executor and Python code generation
│   ├── visual_fallback.py   # Visual fallback (VLM coordinate parsing)
│   ├── history_manager.py   # History manager and code rollback control
│   ├── logs.py              # Logging system based on loguru
│   ├── run_reporter.py      # Structured run output (summary / steps / artifacts)
│   ├── cache/               # Local hybrid semantic cache (exact match + vector retrieval)
│   └── adapters/            # Cross-platform adapters (Android / iOS / Web)
├── utils/
│   ├── utils_xml.py         # Android XML cleanup and dimensionality reduction
│   ├── utils_web.py         # Web DOM compression and URL handling
│   └── screenshot_annotator.py  # Screenshot annotation (ref numbers on screenshots)
├── tests/                   # Framework unit tests (32 test cases)
│   ├── test_ai_heal.py
│   ├── test_executor.py
│   ├── test_screenshot_annotator.py
│   ├── test_utils_web.py
│   └── test_visual_fallback.py
├── docs/
│   ├── agent_guide.md       # Agent integration guide
│   └── capability-matrix.md # Platform/action/locator support matrix
└── test_cases/              # Generated automation test scripts
    ├── android/
    ├── ios/
    └── web/
```

## 📊 Module Call Chain

```text
┌────────────────────────────────────────────────────────────────────┐
│  main.py (Human)    agent_cli.py → cli/dispatch.py (Agent)        │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    ┌──────────┐        ┌───────────┐        ┌─────────────────┐
    │ AIBrain  │        │ UIExecutor│        │StepHistoryManager│
    └────┬─────┘        └─────┬─────┘        └────────┬────────┘
         │                    │                       │
    ┌────▼─────┐         ┌────▼──────┐                │
    │CacheManager│        │ActionHandler│               │
    └──────────┘         └───────────┘                │
                               │                       │
┌──────────────────────────────┴───────────────────────────────┐
│                    BasePlatformAdapter                        │
│            (AndroidU2Adapter / IosWdaAdapter / WebAdapter)   │
└──────────────────────────────────────────────────────────────┘
```

## 🗂️ Cache Architecture

The project implements a **hybrid L1/L2 semantic cache** to reduce LLM API calls dramatically.

### L1 cache: page action cache

- **Best for**: highly similar commands on pages with the same structural skeleton, such as taps
- **Match method**: exact match on UI page fingerprint hash plus instruction semantic hash
- **Hit condition**: 90%+ UI tree structural similarity and an identical instruction

### L2 cache: pure Q&A cache

- **Best for**: repeated questions such as assertions or code generation requests, regardless of the current page
- **Match method**: exact match on instruction semantic hash
- **Hit condition**: identical instruction text, page ignored

### Vector semantic retrieval as fallback

When exact matching misses, the system uses a **Sentence-Transformer** model to compute semantic embeddings for instructions and retrieve the closest cached result. If the similarity reaches the threshold, `L1: 90%`, `L2: 88%`, the cache still hits.

## 📝 Changelog

### 2026-03-30

#### 🏗️ Refactoring

- **EmbeddingModelLoader responsibility split**: extracted model-loading logic from `CacheManager` into a dedicated `EmbeddingModelLoader` class to improve maintainability and testability.
  - The old 85-line `_get_model` method is now a 3-line delegation
  - Model loading, cache cleanup, and network configuration are now clearly separated
  - Dependency injection is supported, which simplifies unit testing

#### 🐛 Bug fixes

- **Platform directory check in `agent_cli.py`**: fixed a bug where platform directories might not exist during dynamic path generation. The engine now creates `test_cases/<platform>/` automatically.
- **Exception handling in `main.py`**: replaced an empty `pass` inside the `finally` block with `log.warning`, so exceptions are no longer swallowed silently.

### Historical versions

- **v0.2.0**: added the hybrid L1/L2 semantic cache system
- **v0.1.0**: initial release with Agentic and Interactive modes

## ❓ FAQ

**Q1: I get `DeviceNotFoundError` or the device cannot connect at runtime. What should I do?**  
Make sure USB debugging is enabled and the device is connected. Run `adb devices` to verify that the device is online. If it is, run `python -m uiautomator2 init` again.

**Q2: The model keeps returning garbled content or actions that cannot be parsed.**  
Check `MODEL_NAME` in `config.py`. Understanding UI structures requires strong reasoning. A flagship-scale model is recommended. If you are using a domestic model provider, prefer one with strong code and JSON output ability.

**Q3: The recorder clicks successfully, but replay fails because it cannot find the element.**  
This is often caused by page animations or slow network loading. Increase `DEFAULT_TIMEOUT` in `config.py`, default `5.0` seconds, to improve tolerance.

**Q4: When should I enable `--vision`?**  
For standard Android native screens, the default XML compression pipeline is usually enough and is both faster and cheaper. But for complex Web H5 canvas pages, Unity game UIs, or dynamic garbled `resource-id`s, `--vision` is strongly recommended so the multimodal model can use screenshots to locate targets accurately.

**Q5: Why does `agent_cli.py` stop with an error in the middle of a run?**  
That means the **self-healing circuit breaker** was triggered. If the engine fails repeatedly on the same page, for example because the target is covered, or the UI becomes stagnant and nothing responds after an action, it stops proactively with a non-zero exit code once `--max_retries` is reached. At that point, inspect the logs, refine your workflow/action design, or provide better context.

**Q6: Video recording does not work.**  
Make sure Scrcpy is installed. Run `scrcpy --version` to verify. If it still fails, check whether the device has granted screen recording permission. Videos for failed cases are attached to the Allure report automatically.

**Q7: The semantic cache does not hit even though I repeated the same action.**  
Check the following:

1. Is the cache enabled? Set `CACHE_ENABLED = True` in `config.py`
2. Has the UI tree changed? L1 cache depends on the page fingerprint, so structural changes can invalidate it
3. Is the instruction identical? L2 cache requires exact text equality

**Q8: The first run is slow and says it is downloading a model.**  
That is expected. On the first run, the Sentence-Transformer model, around 100 MB, must be downloaded. Through a domestic mirror this usually takes 1 to 3 minutes. Later runs use the local cache and are much faster.

**Q9: How do I clear the cache?**

```python
from common.cache import CacheManager
cm = CacheManager()
cm.clear()  # Clear all cache entries
```

## 🐛 Bug Report Guide

If you encounter a problem, please include:

1. **Reproduction steps**: the exact command or sequence of actions
2. **Error logs**: the full error output, including stack traces
3. **Environment info**: operating system, Python version, device model, and OS version
4. **Screenshots or videos**: if the issue involves UI behavior

**Contact**

- Email: jhin.fangz@gmail.com

Thanks for the feedback. I will look into it as soon as possible.
