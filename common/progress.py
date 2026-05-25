"""Rich progress indicators for AI operations."""

import sys
from contextlib import contextmanager

from rich.console import Console

_console = Console(stderr=True)

_TOOL_MODE = False


def set_tool_mode(enabled: bool = True):
    """Disable spinners when running in tool/MCP mode (stdout is structured)."""
    global _TOOL_MODE
    _TOOL_MODE = enabled


@contextmanager
def ai_status(message: str = "Calling AI..."):
    if _TOOL_MODE or not sys.stderr.isatty():
        yield
        return
    with _console.status(f"[bold cyan]{message}[/]", spinner="dots") as status:
        yield status


@contextmanager
def action_status(action: str, target: str = ""):
    label = f"Executing: {action}"
    if target:
        label += f" → {target}"
    if _TOOL_MODE or not sys.stderr.isatty():
        yield
        return
    with _console.status(f"[bold green]{label}[/]", spinner="dots") as status:
        yield status
