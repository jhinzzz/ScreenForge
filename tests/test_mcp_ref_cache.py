"""MF2 guard: web ref cache is bound to the per-session UIExecutor instance.

The ref cache (@N -> element) used to be a process-global on common.executor,
so two inspect_ui calls on different pages shared it and a later `ref @N` action
could resolve against a STALE prior page. The fix binds the cache to the
UIExecutor that _SharedAdapterManager owns per platform: inspect_ui writes it,
a follow-up action reads the SAME instance, and separate sessions can't leak.

These drive the real seam (build_inspect_ui_payload + the manager's executor)
and assert the shared executor's cache reflects the latest inspect — plus that
without a manager (one-shot call) nothing touches a global.
"""

from types import SimpleNamespace

import cli.tool_protocol_handlers as tph
from cli.shared import _SharedAdapterManager


class _FakeAdapter:
    def __init__(self):
        self.driver = object()

    def take_screenshot(self):
        return b""

    def teardown(self):
        pass


def _request(platform="web"):
    return SimpleNamespace(platform=platform, env="dev", vision=False)


def _make_manager(monkeypatch):
    """A manager whose get_or_create yields a fake adapter (no real browser)."""
    mgr = _SharedAdapterManager()
    monkeypatch.setattr(mgr, "get_or_create", lambda platform, env="dev": mgr._adapters.setdefault(platform, _FakeAdapter()))
    return mgr


def _run_inspect(monkeypatch, mgr, ui_json):
    monkeypatch.setattr(
        tph, "_capture_ui_state",
        lambda args, adapter, reporter, step: (ui_json, None),
    )
    return tph.build_inspect_ui_payload(_request("web"), shared_adapter_manager=mgr)


def test_inspect_ui_syncs_shared_executor_to_latest_page(monkeypatch):
    mgr = _make_manager(monkeypatch)
    page_a = '{"ui_elements":[{"ref":"@1","id":"login-btn","text":"Login"}]}'
    page_b = '{"ui_elements":[{"ref":"@1","id":"logout-btn","text":"Logout"}]}'

    payload_a = _run_inspect(monkeypatch, mgr, page_a)
    assert payload_a["ok"] is True
    executor = mgr.get_executor("web")
    assert executor.resolve_ref("@1")["id"] == "login-btn"

    # Second inspect on a different page must overwrite the SAME executor's
    # cache, not leak @1 from the previous page.
    payload_b = _run_inspect(monkeypatch, mgr, page_b)
    assert payload_b["ok"] is True
    assert executor.resolve_ref("@1")["id"] == "logout-btn", (
        "ref @1 leaked from the previous page — shared executor cache not updated"
    )


def test_inspect_ui_empty_page_clears_stale_refs(monkeypatch):
    mgr = _make_manager(monkeypatch)
    _run_inspect(monkeypatch, mgr, '{"ui_elements":[{"ref":"@1","id":"x"}]}')
    executor = mgr.get_executor("web")
    assert executor.resolve_ref("@1") is not None

    # An inspect that finds no elements must not leave the old @1 resolvable.
    _run_inspect(monkeypatch, mgr, '{"ui_elements":[]}')
    assert executor.resolve_ref("@1") is None


def test_inspect_ui_without_manager_does_not_crash(monkeypatch):
    # One-shot tool call (no manager): nothing to share with, so the ref-cache
    # sync is skipped — the inspect must still succeed.
    monkeypatch.setattr(tph, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(
        tph, "_capture_ui_state",
        lambda args, adapter, reporter, step: ('{"ui_elements":[{"ref":"@1","id":"x"}]}', None),
    )
    payload = tph.build_inspect_ui_payload(_request("web"))
    assert payload["ok"] is True
    assert payload["element_count"] == 1
