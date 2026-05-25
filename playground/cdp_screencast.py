"""CDP Screencast: streams live screenshots from Chrome DevTools Protocol."""

import asyncio
import json
import logging

import websockets

logger = logging.getLogger(__name__)

DEFAULT_CDP_HTTP = "http://127.0.0.1:9333"


async def _get_ws_url(cdp_http_url: str) -> str:
    """Fetch the debugger websocket URL from Chrome's /json/version endpoint."""
    import urllib.request

    version_url = cdp_http_url.rstrip("/") + "/json/version"
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None, lambda: urllib.request.urlopen(version_url, timeout=3).read()
    )
    data = json.loads(resp)
    return data["webSocketDebuggerUrl"]


async def run_screencast(
    on_frame,
    cdp_http_url: str = DEFAULT_CDP_HTTP,
    fps: int = 2,
    quality: int = 60,
    max_width: int = 1280,
    max_height: int = 900,
):
    """Connect to Chrome CDP and stream screencast frames.

    Args:
        on_frame: async callable receiving (base64_png: str, metadata: dict)
        cdp_http_url: Chrome's HTTP debug URL (e.g. http://127.0.0.1:9333)
        fps: target frames per second
        quality: JPEG quality (1-100)
        max_width: max frame width
        max_height: max frame height
    """
    ws_url = await _get_ws_url(cdp_http_url)
    logger.info(f"Connecting to CDP websocket: {ws_url}")

    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        msg_id = 1

        # Start screencast
        await ws.send(json.dumps({
            "id": msg_id,
            "method": "Page.startScreencast",
            "params": {
                "format": "jpeg",
                "quality": quality,
                "maxWidth": max_width,
                "maxHeight": max_height,
                "everyNthFrame": max(1, 60 // fps),
            },
        }))
        msg_id += 1

        async for raw_msg in ws:
            msg = json.loads(raw_msg)
            method = msg.get("method", "")

            if method == "Page.screencastFrame":
                params = msg.get("params", {})
                session_id = params.get("sessionId", 0)
                frame_data = params.get("data", "")
                metadata = params.get("metadata", {})

                # Acknowledge frame so Chrome sends the next one
                await ws.send(json.dumps({
                    "id": msg_id,
                    "method": "Page.screencastFrameAck",
                    "params": {"sessionId": session_id},
                }))
                msg_id += 1

                if frame_data:
                    await on_frame(frame_data, metadata)


async def run_screencast_safe(on_frame, cdp_http_url: str = DEFAULT_CDP_HTTP, **kwargs):
    """Run screencast with auto-reconnect on failure."""
    while True:
        try:
            await run_screencast(on_frame, cdp_http_url=cdp_http_url, **kwargs)
        except Exception as e:
            logger.warning(f"CDP screencast disconnected: {e}. Reconnecting in 2s...")
            await asyncio.sleep(2)
