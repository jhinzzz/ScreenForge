"""MF2 guard: web ref cache must track the latest inspect, not leak across pages.

The ref cache (_cached_ui_elements) is a process-global. Under the long-lived
MCP server, two inspect_ui calls on different pages share that global, so a
later `--action ref @N` could resolve against a STALE prior page. Previously:
  - build_inspect_ui_payload never wrote the cache at all, and
  - the executor only auto-refreshed when the cache was EMPTY.

This drives the real seam (build_inspect_ui_payload) twice with different pages
and asserts the executor's ref cache reflects the latest inspect.
"""

from types import SimpleNamespace

import cli.tool_protocol_handlers as tph
import common.executor as executor


class _FakeAdapter:
    def __init__(self):
        self.driver = object()

    def take_screenshot(self):
        return b""

    def teardown(self):
        pass


def _request(platform="web"):
    return SimpleNamespace(platform=platform, env="dev", vision=False)


def _run_inspect(monkeypatch, ui_json):
    monkeypatch.setattr(tph, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(
        tph, "_capture_ui_state",
        lambda args, adapter, reporter, step: (ui_json, None),
    )
    return tph.build_inspect_ui_payload(_request("web"))


def test_inspect_ui_syncs_ref_cache_to_latest_page(monkeypatch):
    page_a = '{"ui_elements":[{"ref":"@1","id":"login-btn","text":"Login"}]}'
    page_b = '{"ui_elements":[{"ref":"@1","id":"logout-btn","text":"Logout"}]}'

    payload_a = _run_inspect(monkeypatch, page_a)
    assert payload_a["ok"] is True
    assert executor._resolve_ref("@1")["id"] == "login-btn"

    # Second inspect on a different page must overwrite the cache, not leak @1.
    payload_b = _run_inspect(monkeypatch, page_b)
    assert payload_b["ok"] is True
    assert executor._resolve_ref("@1")["id"] == "logout-btn", (
        "ref @1 leaked from the previous page — MCP ref cache not isolated"
    )


def test_inspect_ui_empty_page_clears_stale_refs(monkeypatch):
    page = '{"ui_elements":[{"ref":"@1","id":"x"}]}'
    _run_inspect(monkeypatch, page)
    assert executor._resolve_ref("@1") is not None

    # An inspect that finds no elements must not leave the old @1 resolvable.
    _run_inspect(monkeypatch, '{"ui_elements":[]}')
    assert executor._resolve_ref("@1") is None
