"""Fire-and-forget visualization sink: short-lived action process → resident playground.

Red line (G5): any network error is swallowed silently. A sink push MUST NEVER
slow down the action or change its exit code — the 0/1 exit code is a contract to
the agent (see CLAUDE.md). The sink is a bypass observer hung after save_to_disk;
it does not touch execute_and_record, codegen, or disk persistence.
"""

import base64
import threading

import requests  # already in requirements.txt (requests==2.32.5) — zero new deps
from loguru import logger as log
from pydantic import BaseModel, Field

from cli.session import load_session

DEFAULT_PLAYGROUND_URL = "http://127.0.0.1:7860"

# Latency ceiling on the contract-protected single-step --action path (red line #1:
# "never slow the action down"). A reachable-but-slow playground must not tax the
# action beyond this documented budget. (connect, read) is split so a hung peer
# can't stall on connect; _JOIN_TIMEOUT is the hard cap the single-step process
# waits for the last frame to land before sys.exit — kept ≤ read+ε and well under
# human-perceptible. Worst added latency on --action ≈ _JOIN_TIMEOUT.
_POST_TIMEOUT = (0.2, 0.25)  # (connect, read) seconds
_JOIN_TIMEOUT = 0.3  # seconds; single-step last-frame grace


class PlaygroundStepEvent(BaseModel):
    """One step pushed to the playground. Shape == the frontend SSE `step` contract."""

    run_id: str
    step_index: int  # ⭐ time-travel seed: data accumulates/replays by this index
    code_lines: list[str] = Field(default_factory=list)
    action_description: str = ""
    action: str = ""
    locator_type: str = ""
    locator_value: str = ""
    extra_value: str = ""
    success: bool = True
    screenshot_b64: str = ""  # empty = no screenshot this step (degrade, never crash)


class PlaygroundSink:
    """Pushes each step to a running playground, best-effort.

    Disabled by default: enabled=False means zero cost — no HTTP, no thread, and
    (at the call sites) take_screenshot is never even invoked.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_PLAYGROUND_URL,
        enabled: bool = False,
        join_on_exit: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled
        # Single-step --action exits the process right after push_step returns;
        # join a short window so the daemon thread's last frame can land (§6 单步收尾).
        self._join_on_exit = join_on_exit

    def push_step(self, event: PlaygroundStepEvent) -> None:
        """Best-effort push. Hands off to a daemon thread; the caller returns at
        once (arch#3: never block the action hot path)."""
        if not self.enabled:
            return
        t = threading.Thread(target=self._post, args=(event,), daemon=True)
        t.start()
        if self._join_on_exit:
            # Single-step --action exits right after this returns; wait a bounded
            # grace (≤ _JOIN_TIMEOUT) for the last frame to land. This is the hard
            # ceiling on added latency to the contract path — never grow it past a
            # human-imperceptible budget (HIGH-1 from review: 0.6s was too generous).
            t.join(timeout=_JOIN_TIMEOUT)

    def _post(self, event: PlaygroundStepEvent) -> None:
        try:
            requests.post(
                f"{self.base_url}/api/step",
                json=event.model_dump(),
                timeout=_POST_TIMEOUT,  # (connect, read) split: a hung playground can't stall us
            )
        except Exception as e:  # ConnectionError / Timeout / anything — swallow (G5)
            log.debug(f"[playground-sink] skip (playground unreachable): {e}")

    @staticmethod
    def encode_screenshot(adapter) -> str:
        """Cross-platform: take_screenshot() -> bytes → base64. Can't grab → '' (degrade).

        Platform-agnostic on purpose: all three adapters expose take_screenshot()
        (base_adapter.py:17 abstract), so no per-platform branching is needed here.
        """
        try:
            png = adapter.take_screenshot()
            return base64.b64encode(png).decode() if png else ""
        except Exception as e:
            log.debug(f"[playground-sink] screenshot skip: {e}")
            return ""


def build_step_event(
    *,
    run_key: str,
    step_index: int,
    action_data: dict,
    result: dict,
    screenshot_b64: str,
) -> PlaygroundStepEvent:
    """MANDATORY single construction point for every step event (code#4).

    All three entry points (action / workflow / main) build events ONLY through
    here. Adding a field later (e.g. a seed timestamp) is then one edit, not three
    — preventing the P9-style schema split where one call site silently drifts.
    """
    return PlaygroundStepEvent(
        run_id=run_key,
        step_index=step_index,
        code_lines=result.get("code_lines", []) or [],
        action_description=result.get("action_description", ""),
        action=action_data.get("action", ""),
        locator_type=action_data.get("locator_type", ""),
        locator_value=action_data.get("locator_value", ""),
        extra_value=action_data.get("extra_value", ""),
        success=bool(result.get("success", True)),
        screenshot_b64=screenshot_b64,
    )


def build_sink_from_args(args, *, join_on_exit: bool = False) -> "PlaygroundSink":
    """Construct a sink from parsed CLI args. Absent flags → disabled (zero cost)."""
    return PlaygroundSink(
        base_url=getattr(args, "playground_url", "") or DEFAULT_PLAYGROUND_URL,
        enabled=bool(getattr(args, "playground_sink", False)),
        join_on_exit=join_on_exit,
    )


def maybe_push_step(
    sink: "PlaygroundSink",
    *,
    args,
    reporter,
    adapter,
    action_data: dict,
    result: dict,
    step_index: int | None = None,
) -> None:
    """The ONE guarded entry point every call site uses (action / workflow / main).

    Disabled-fast: returns before touching the adapter, so take_screenshot is
    never called and there is zero device I/O or network on the hot path when the
    sink is off. Wrapped in a blanket try/except as a belt-and-suspenders G5
    guard — the bypass observer must never break the action it observes.
    """
    if not sink.enabled:
        return
    try:
        run_key, resolved_index = resolve_playground_run_key(args, reporter)
        event = build_step_event(
            run_key=run_key,
            step_index=step_index if step_index is not None else resolved_index,
            action_data=action_data,
            result=result,
            screenshot_b64=PlaygroundSink.encode_screenshot(adapter),
        )
        sink.push_step(event)
    except Exception as e:  # never let visualization break the observed action
        log.debug(f"[playground-sink] push skipped: {e}")


def resolve_playground_run_key(args, reporter) -> tuple[str, int]:
    """Return (run_key, step_index) — the cross-process-stable playground timeline key.

    Root cause (arch#1): run_reporter.py mints run_id as `timestamp_uuid`, unique
    per short-lived process. In agent mode each --action is its own process, so
    using reporter.run_id directly would shatter a 5-step flow into 5 single-step
    buckets and the seed's timeline would be born broken.

    --session-id present → use session_id as the key (one session = one timeline);
      step_index comes from the session's persisted 'steps' counter (cli/session.py),
      which dispatch.py increments AFTER each successful step, so steps+1 is the
      1-based index of the step about to be pushed.
    No session → a bare --action is inherently single-step: reporter.run_id, index 1.
    """
    session_id = getattr(args, "session_id", "") or getattr(args, "session_end", "")
    if session_id:
        session = load_session(session_id)
        return session_id, (session.get("steps", 0) + 1 if session else 1)
    return reporter.run_id, 1
