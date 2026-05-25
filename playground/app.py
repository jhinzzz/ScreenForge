"""Playground server: live screenshot viewer + action history via SSE."""

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from playground.cdp_screencast import DEFAULT_CDP_HTTP, run_screencast_safe

logger = logging.getLogger(__name__)

app = FastAPI(title="ScreenForge Playground")
_cdp_url: str = DEFAULT_CDP_HTTP
_screencast_task: asyncio.Task | None = None

_action_log: list[dict] = []
_screenshot_b64: str = ""
_subscribers: list[asyncio.Queue] = []


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
