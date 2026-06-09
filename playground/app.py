"""Playground server: live screenshot viewer + action history via SSE."""

import asyncio
import json
import logging
import shutil
import subprocess
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from playground.cdp_screencast import DEFAULT_CDP_HTTP, run_screencast_safe

logger = logging.getLogger(__name__)

# Known editor CLIs, in detection-preference order. Each opens a file at a line
# via the VSCode-family `-g <file>:<line>` contract (VSCode + every fork share it);
# Zed uses `<file>:<line>`; plain vim/nvim use `+<line> <file>`. We only ever run
# the resolved absolute CLI path (shutil.which) with these fixed arg shapes —
# never a shell string — so a crafted file path can't inject a command.
_EDITORS: list[dict] = [
    {"id": "trae", "label": "Trae", "bin": "trae", "args": "goto"},
    {"id": "code", "label": "VS Code", "bin": "code", "args": "goto"},
    {"id": "cursor", "label": "Cursor", "bin": "cursor", "args": "goto"},
    {"id": "windsurf", "label": "Windsurf", "bin": "windsurf", "args": "goto"},
    {"id": "zed", "label": "Zed", "bin": "zed", "args": "colon"},
    {"id": "subl", "label": "Sublime Text", "bin": "subl", "args": "colon"},
    {"id": "idea", "label": "IntelliJ IDEA", "bin": "idea", "args": "line-flag"},
    {"id": "pycharm", "label": "PyCharm", "bin": "pycharm", "args": "line-flag"},
    {"id": "nvim", "label": "Neovim", "bin": "nvim", "args": "plus"},
    {"id": "vim", "label": "Vim", "bin": "vim", "args": "plus"},
]


def _detect_editors() -> list[dict]:
    """Return the installed editors (those whose CLI is on PATH), preference-ordered.

    Pure PATH probe via shutil.which — no subprocess, no side effects. The resolved
    absolute path is kept server-side only (not sent to the browser) so the open
    endpoint never trusts a client-supplied binary path.
    """
    found = []
    for ed in _EDITORS:
        path = shutil.which(ed["bin"])
        if path:
            found.append({"id": ed["id"], "label": ed["label"], "_path": path, "_args": ed["args"]})
    return found


def _build_open_command(editor: dict, file_path: str, line: int) -> list[str]:
    """Build the argv list (never a shell string) to open file_path at line."""
    style = editor["_args"]
    exe = editor["_path"]
    if style == "goto":  # VSCode family: code -g file:line
        return [exe, "-g", f"{file_path}:{line}"]
    if style == "colon":  # zed / sublime: editor file:line
        return [exe, f"{file_path}:{line}"]
    if style == "line-flag":  # JetBrains: idea --line N file
        return [exe, "--line", str(line), file_path]
    if style == "plus":  # vim family: vim +N file
        return [exe, f"+{line}", file_path]
    return [exe, file_path]

app = FastAPI(title="ScreenForge Playground")
_cdp_url: str = DEFAULT_CDP_HTTP
_screencast_task: asyncio.Task | None = None

_action_log: list[dict] = []
_screenshot_b64: str = ""
_subscribers: list[asyncio.Queue] = []

# ⭐ Time-travel seed (G6): steps accumulate by run_id → step_index so a future
# Form-B filmstrip can index this array with zero execution-flow rework.
# arch#2: memory is bounded — base64 frames are NEVER retained here (only the
# single live-frame slot + SSE carry them); the log holds metadata + disk paths.
_MAX_RUNS = 20  # total distinct runs kept (LRU-evicted)
_MAX_STEPS_PER_RUN = 500  # per-run step cap (oldest head truncated)
_step_log: "OrderedDict[str, list[dict]]" = OrderedDict()


def push_event(event_type: str, data: dict) -> None:
    payload = {"type": event_type, "ts": time.time(), **data}
    if event_type == "action":
        _action_log.append(payload)
        if len(_action_log) > 200:
            _action_log.pop(0)
    for q in _subscribers:
        q.put_nowait(payload)


def update_screenshot(b64_png: str) -> None:
    global _screenshot_b64
    _screenshot_b64 = b64_png
    push_event("screenshot", {"size": len(b64_png)})


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text())


@app.get("/api/screenshot")
async def get_screenshot():
    return {"b64": _screenshot_b64}


@app.get("/api/actions")
async def get_actions():
    return {"actions": _action_log[-50:]}


@app.post("/api/action")
async def post_action(request: Request):
    body = await request.json()
    push_event("action", body)
    return {"ok": True}


@app.post("/api/screenshot")
async def post_screenshot(request: Request):
    body = await request.json()
    b64 = body.get("b64", "")
    if b64:
        update_screenshot(b64)
    return {"ok": True}


@app.post("/api/step")
async def post_step(request: Request):
    """Receive one step from a short-lived action process (the live-mirror sink).

    The base64 frame goes to the single live-frame slot + SSE for real-time
    display; it is deliberately NOT retained in _step_log (arch#2: bounded memory).
    _step_log keeps only step metadata (code_lines + action/locator), so a long
    run can't balloon RAM. Note the seed therefore carries no frame reference yet:
    a future phase that wants replay would add a screenshot_path here (the sink
    sends no such field today — see PlaygroundStepEvent in cli/playground_sink.py).
    """
    global _screenshot_b64
    body = await request.json()
    run_id = body.get("run_id", "default")
    b64 = body.pop("screenshot_b64", "")  # pop: keep base64 OUT of _step_log
    if b64:
        # Update the latest-frame slot for /api/screenshot backfill, but DON'T
        # fire a separate "screenshot" SSE event: the "step" event below already
        # carries this frame inline. Pushing both makes the client race-fetch the
        # slot and re-render with the wrong mime prefix. (The CDP screencast path
        # still uses update_screenshot()'s event for its frame-only stream.)
        _screenshot_b64 = b64

    steps = _step_log.setdefault(run_id, [])
    # De-dup by step_index, last-writer-wins: a failed/retried session step can push
    # the same index twice (the session 'steps' counter only advances on success),
    # and the seed timeline indexes by step_index — a duplicate would show an
    # ambiguous frame. Overwrite in place so each index maps to exactly one step.
    step_idx = body.get("step_index")
    for i, existing in enumerate(steps):
        if existing.get("step_index") == step_idx:
            steps[i] = body
            break
    else:
        steps.append(body)
    if len(steps) > _MAX_STEPS_PER_RUN:
        del steps[: len(steps) - _MAX_STEPS_PER_RUN]  # truncate oldest head
    _step_log.move_to_end(run_id)  # LRU: most-recently-active run to the tail
    while len(_step_log) > _MAX_RUNS:
        _step_log.popitem(last=False)  # evict the least-recently-active run

    push_event("step", {**body, "screenshot_b64": b64})  # SSE still carries b64
    return {"ok": True}


@app.get("/api/run/{run_id}/steps")
async def get_run_steps(run_id: str):
    """⭐ Time-travel seed (G6): the data exit for Form B (time travel).

    Phase 1 builds the endpoint + accumulation; the frontend filmstrip is a
    skeleton with no replay logic yet. Form B later == a pure-frontend timeline
    UI indexing this array — zero rework to the execution flow or sink.
    """
    return {"run_id": run_id, "steps": _step_log.get(run_id, [])}


@app.get("/api/editors")
async def get_editors():
    """List installed editors for the 'Open in <IDE>' control.

    Returns only id + label (the resolved binary path stays server-side). Empty
    list → the frontend disables the button and explains no editor was found.
    """
    eds = _detect_editors()
    return {"editors": [{"id": e["id"], "label": e["label"]} for e in eds]}


@app.post("/api/open")
async def open_in_editor(request: Request):
    """Open a generated test file at a line in the chosen (or first detected) editor.

    Safety: loopback-only server (host 127.0.0.1), and we launch the resolved
    absolute CLI path with a fixed argv shape — never a shell string — so the file
    path can't inject a command. The file must exist (a missing/bogus path is
    rejected) and the editor id must be one we actually detected on PATH.
    """
    body = await request.json()
    file_path = str(body.get("file_path", "")).strip()
    editor_id = str(body.get("editor", "")).strip()
    try:
        line = int(body.get("line", 1) or 1)
    except (TypeError, ValueError):
        line = 1

    if not file_path:
        return {"ok": False, "error": "no file_path"}
    resolved = Path(file_path).expanduser()
    if not resolved.is_file():
        return {"ok": False, "error": f"file not found: {file_path}"}

    detected = _detect_editors()
    if not detected:
        return {"ok": False, "error": "no editor detected on PATH"}
    editor = next((e for e in detected if e["id"] == editor_id), None) if editor_id else None
    if editor is None:
        editor = detected[0]  # caller sent none/unknown → first detected (preference order)

    cmd = _build_open_command(editor, str(resolved), line)
    try:
        # Fire-and-forget: don't block the request on the editor process. No shell.
        subprocess.Popen(cmd)  # noqa: S603 — fixed argv, resolved abs path, loopback-only
    except Exception as e:
        logger.warning(f"open_in_editor failed: {e}")
        return {"ok": False, "error": str(e), "editor": editor["id"]}
    return {"ok": True, "editor": editor["id"], "label": editor["label"]}


@app.get("/api/events")
async def sse_events():
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.append(queue)

    async def event_stream():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.remove(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.on_event("startup")
async def _start_screencast():
    global _screencast_task

    async def _on_frame(b64_data: str, metadata: dict):
        update_screenshot(b64_data)

    _screencast_task = asyncio.create_task(
        run_screencast_safe(_on_frame, cdp_http_url=_cdp_url)
    )
    logger.info(f"CDP screencast started (target: {_cdp_url})")


@app.on_event("shutdown")
async def _stop_screencast():
    global _screencast_task
    if _screencast_task:
        _screencast_task.cancel()
        _screencast_task = None


def run_server(host: str = "127.0.0.1", port: int = 7860, cdp_url: str = DEFAULT_CDP_HTTP):
    global _cdp_url
    _cdp_url = cdp_url

    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
