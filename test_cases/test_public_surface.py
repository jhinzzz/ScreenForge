# -*- coding: utf-8 -*-
"""Public-surface contract test (audit guardrail, 2026-06-02).

ScreenForge's CLI package was refactored so that ``agent_cli.py`` is now a thin
6-line shim delegating to ``cli.dispatch.main``. Twice now, that move silently
dropped names other modules/tests reached for, surfacing as a scatter of
``AttributeError``s deep in unrelated tests.

This test pins the public symbols that tests, the MCP server, and external
agents depend on. If a future refactor renames or relocates one of these, this
test fails fast at the contract boundary with a clear message — instead of five
mystery AttributeErrors elsewhere.

If you intentionally move a symbol, update BOTH this list and every caller.
"""

import importlib

import pytest

# module path -> attribute names that must exist on it
_REQUIRED_SURFACE = {
    "cli.dispatch": [
        "main",
        "_dispatch_execution",
        "_run_session_end",
    ],
    "cli.tool_protocol_handlers": [
        "build_tool_response_payload",
        "build_inspect_ui_payload",
        "build_load_case_memory_payload",
        "build_load_run_payload",
        "run_tool_request_mode",
        "run_tool_stdin_mode",
        "run_mcp_server_mode",
        "_list_run_dirs",
        "_resolve_new_run_dir",
        "_requires_model_runtime",
        # re-exported from cli.shared; patched here in tests, so must resolve here
        "_connect_adapter",
        "_capture_ui_state",
    ],
    "cli.shared": [
        "_connect_adapter",
        "_capture_ui_state",
        "_create_adapter",
        "launch_app",
        "save_to_disk",
        "get_initial_header",
        "AndroidU2Adapter",  # module-level name (lazy-bound); used as patch target
    ],
}


@pytest.mark.parametrize(
    "module_path,attr",
    [(mod, attr) for mod, attrs in _REQUIRED_SURFACE.items() for attr in attrs],
)
def test_public_surface_symbol_exists(module_path, attr):
    module = importlib.import_module(module_path)
    assert hasattr(module, attr), (
        f"Public-surface contract broken: '{module_path}.{attr}' is missing. "
        f"A refactor likely moved or renamed it. Update callers AND this contract "
        f"list (test_cases/test_public_surface.py) together."
    )


def test_agent_cli_shim_delegates_to_dispatch_main():
    """agent_cli.py must stay a shim that re-exports cli.dispatch.main."""
    import agent_cli
    from cli.dispatch import main as dispatch_main

    assert agent_cli.main is dispatch_main, (
        "agent_cli.main must be cli.dispatch.main. The compatibility shim drifted."
    )
