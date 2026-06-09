# Playground Live Mirror — Guide

**[中文](./playground-guide_CN.md)** | English

> **In one line**: run a test with ScreenForge while watching, live in your browser, the **generated pytest code grow line-by-line + a screenshot of the page at every step**.
>
> This is a **user-facing quickstart**. For the architecture, red-line contract, and memory model, see [capability-matrix.md](./capability-matrix.md#playground-live-mirror-2026-06).

---

## Mental model: this is two processes

The Live Mirror **is not one command** — it's **two processes working together**, which is the easiest place to trip up:

```
┌─────────────────────────────┐         ┌──────────────────────────────────┐
│  Process 1: viewer server    │  HTTP   │  Process 2: executor (per/multi)   │
│  screenforge --playground    │◄────────┤  screenforge --action ...         │
│                              │  POST   │            --playground-sink       │
│  long-lived, :7860          │  /step  │            --session-id <name>     │
│  open it in your browser     │         │  exits when done; pushes each step │
└─────────────────────────────┘         └──────────────────────────────────┘
         ▲
         │ browser visits http://127.0.0.1:7860
        (you)
```

- **Process 1 (server)**: `screenforge --playground`, long-lived on `:7860`. **You open it in your browser.** It never drives any page itself — it only displays.
- **Process 2 (executor)**: the `--action` / `--workflow` / `main.py` that actually drives the UI. With `--playground-sink` added, every time it completes a step it pushes the **code + screenshot** to Process 1.

> **Why two processes?** The executor is **short-lived** — one `--action` runs and exits. The viewer must stay alive to keep displaying, so it's a standalone server. The two communicate over HTTP (no shared memory).

---

## Quickstart (Web, the easiest path)

### Step 1: start the server (terminal A, long-lived)

```bash
screenforge --playground
# → Starting Playground on http://127.0.0.1:7860
```

Open **http://127.0.0.1:7860** in your browser. It's empty for now, waiting to receive steps.

> If the startup logs repeatedly show `CDP screencast disconnected: Connection refused ... Reconnecting` — that's **normal and harmless**, see [Troubleshooting](#troubleshooting).

### Step 2: feed steps in (terminal B)

**Key point: multiple steps must carry the same `--session-id`**, otherwise they won't connect into one timeline (see the next section).

```bash
# Step 1: open the page
screenforge --action goto --platform web \
  --extra-value "https://example.com" \
  --session-id demo --playground-sink --json

# Step 2: assert the title exists
screenforge --action assert_exist --platform web \
  --locator-type text --locator-value "Example Domain" \
  --session-id demo --playground-sink --json

# Step 3: click the link
screenforge --action click --platform web \
  --locator-type text --locator-value "Learn more" \
  --session-id demo --playground-sink --json
```

Each time one runs, the browser **immediately** gains another line of code + one frame screenshot. After all three run, you'll see a complete `demo` timeline: `goto → assert → click`.

> The first `--action --platform web` automatically launches a **visible Chromium** (persistent, reused by later commands). This also incidentally clears that `Connection refused` log from Step 1.

---

## Why must multiple steps carry `--session-id`? (the most important point)

This is the **implicit but critical** contract:

- **Every bare `--action` command is its own process, with its own random `run_id`.**
- Playground splits steps into different **timeline buckets** by `run_id`.
- So **multiple commands without `--session-id` each land in a different bucket** — what you see isn't one continuous 5-step flow, but 5 unrelated single-step records.

`--session-id <name>` makes multiple commands **share one `run_id`**, which:

1. keeps step numbers continuous (1, 2, 3…) instead of each restarting from 1;
2. renders as **one** timeline in the playground;
3. archives to the same session directory on disk too.

> **One session = one timeline.** Switch session (or run bare with no session), and the playground will **clear history and restart** a new timeline — it won't mix the steps of two flows together.

When done, wrap up (optional, archives that session):

```bash
screenforge --session-end demo
```

### With a workflow it's naturally continuous — no session-id needed

A multi-step YAML is a **single-process loop**, so its steps are naturally continuous — just turn on the sink:

```bash
screenforge --workflow ./workflows/login.yaml --platform web \
  --playground-sink --json
```

---

## Human recording mode (main.py)

Interactive recording (you type natural language, the AI decides) can mirror too:

```bash
python main.py --platform web --playground-sink
```

The whole recording session is pushed continuously as one timeline — the counterpart to Cypress Studio's "record while you watch."

---

## Options at a glance

| Option | Which process | Description |
|---|---|---|
| `--playground` | server | start the long-lived viewer process |
| `--playground-port <N>` | server | change the port (default `7860`) |
| `--playground-sink` | executor | **switch**: push each step to the server (**off by default**, zero overhead when off) |
| `--playground-url <URL>` | executor | server address (default `http://127.0.0.1:7860`) |
| `--session-id <name>` | executor | **required for multiple steps**: bind multiple commands into one timeline |

> `--playground-sink` is off by default — pure CI / agent test runs have **zero overhead** (not even a screenshot is captured). Turn it on only when you want to "watch as you write."

---

## Interface features

### Open the generated test case in your IDE in one click

The top bar has an **"Open in <your IDE>"** button. On startup the playground **auto-scans your PATH for installed editors** (VS Code / Trae / Cursor / Windsurf / Zed / Sublime / IntelliJ / PyCharm / Vim / Neovim), and the button label changes accordingly — for instance, if you have Trae installed, it shows "Open in Trae."

- **Click the button** (or press `⌘E` / `Ctrl-E`): open the `test_*.py` **currently being generated** in the selected editor, jumping to the latest line.
- **Click the `▾` on the right**: a dropdown to switch editors; **your choice is saved to `localStorage`** and used automatically next time.
- If you have several installed, they're all listed; when **none is detected** the button is automatically disabled, prompting you to install an editor with a CLI (such as `code` / `trae`).

> The open action is performed by the **long-lived playground process** (it runs a command like `trae -g <file>:<line>`) — the browser itself can't spawn processes. The server binds only `127.0.0.1` and calls with a fixed argument list (not a shell string), so a file path can't be injected as a command.

### Connection-status indicator (Live / Idle / Disconnected)

The status dot on the right of the top bar faithfully reflects whether the **target device/page** is still producing steps, rather than only the browser-to-server connection:

| Status | Meaning |
|---|---|
| 🟢 **Live** | continuously receiving steps/screenshots (running) |
| 🟡 **Idle** | connection is fine, but the target has been **quiet ~4s** (run finished or paused) — not an error |
| 🔴 **Disconnected** | the SSE to the playground really dropped (the server is gone) |

> Why Idle is needed: the browser-to-playground SSE is **long-lived** and is always "connected." So after a run finishes, looking at the connection alone would keep showing green — a fake "Live." It's changed to be **judged by activity**: more than ~4s with no new step degrades to Idle (amber, the screenshot corner badge also flips to `IDLE`); when the next step arrives it automatically switches back to Live.

### Light / dark theme toggle

The top bar's **☀/🌙 button** toggles between the light and dark themes:

- **Dark (default)**: forge style — near-black ground + molten-orange (ember) signal color, a developer-tools feel.
- **Light**: "cooled steel · blueprint paper" — a warm paper surface + ink-blue text, with the same ember mark deepened to `#ea580c` to meet WCAG AA contrast on the light ground; the code highlighting gets a separate light-only ink-toned Prism palette (function names keep the brand orange).
- **Memory**: the choice is written to `localStorage`; next time it opens **the first paint already renders in the last theme** (preset inside `<head>`, no black/white flash). If you've never chosen, it follows the system `prefers-color-scheme`.

> The **page under test** in the screenshot area is always shown as-is (it won't be forced white under the light theme) — the playground only switches its own interface shell, not the look of your app.

### Time-travel (click a frame to rewind)

Every item in the bottom **filmstrip** and the bottom-right **step history** is clickable: click any frame / step and the large screenshot on the left **jumps back to that step's view**, while the code column on the right **highlights the corresponding line**. All three (screenshot / code / history) move together.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| startup logs spamming `CDP screencast disconnected: Connection refused` | the server is waiting for a browser that isn't up yet (CDP `:9333`). This is Web's **continuous-frame preview** add-on layer, **unrelated** to the sink push. | **Harmless, ignore it.** It disappears once the first `--action --platform web` brings up a browser. |
| two `#1` steps in the browser / step counts don't add up | you fed **multiple commands without `--session-id`** (or across different sessions), and multiple timelines got merged together. | Carry the **same** `--session-id` across all steps. When you switch session the playground auto-clears and restarts. |
| the page stays blank with no steps at all | the executor didn't carry `--playground-sink`, or `--playground-url` points at the wrong address/port. | Add `--playground-sink` to the executor command, and confirm the URL matches the server port. |
| `Address already in use` / port taken | `:7860` is already occupied (perhaps last time's server didn't exit). | Switch ports with `--playground-port 7861` (and match `--playground-url http://127.0.0.1:7861` on the executor side), or kill the occupying process first. |
| `[E013] Playground requires extra dependencies` | the playground extra isn't installed. | `pip install screenforge[playground]` (includes `fastapi`/`uvicorn`/`websockets`). |
| a step has only code, no screenshot | that step's screenshot capture failed on its own (degrade tolerance). | By design: execution is **never** interrupted by a failed screenshot; the code is still pushed. |
| the "Open in IDE" button is greyed out / shows "No editor found" | the playground found no installed editor's CLI on PATH. | Install an editor's command-line entry (VS Code: command palette → "Shell Command: Install 'code' command"; Trae/Cursor likewise). Restart the playground after installing. |
| the run finished but the status still shows green `Live` | old behavior. It's now judged by activity: ~4s with no new step auto-switches to `Idle`. | Upgrade to a version with this change; if it's still long-green, confirm you're looking at the latest `index.html`. |

---

## Boundaries (current version)

- **Code column is read-only**: editing code in the playground to write it back isn't supported this round (it would conflict with codegen's automatic save-to-disk).
- **Time-travel is in-session rewind**: clicking a frame/step jumps the screenshot + highlights the code within the **current run** (see above). Persisted replay of historical frames across sessions (paging through old runs after closing the page) is left for a future iteration.
- **Mobile "live" is step-wise**: Android/iOS take roughly 0.5–2s per screenshot (the device's physical ceiling), so the front end faithfully presents discrete snapshots and doesn't fake a continuous video.

For the deeper architecture and red-line contract, see [capability-matrix.md](./capability-matrix.md#playground-live-mirror-2026-06).
