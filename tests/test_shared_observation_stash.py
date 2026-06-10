"""The MCP observation stash on _SharedAdapterManager.

The execute mode stashes ONE live post-action observation here; the MCP handler
reads it after dispatch. take_* clears on read so a later execute in the same
session can never serve a stale prior step's observation.
"""

from cli.shared import _SharedAdapterManager


def test_empty_manager_returns_none():
    mgr = _SharedAdapterManager()
    assert mgr.take_last_observation() is None


def test_set_then_take_returns_payload():
    mgr = _SharedAdapterManager()
    payload = {"ok": True, "ui_tree": {"ui_elements": []}, "element_count": 0}
    mgr.set_last_observation(payload)
    assert mgr.take_last_observation() == payload


def test_take_clears_on_read():
    mgr = _SharedAdapterManager()
    mgr.set_last_observation({"ok": True})
    mgr.take_last_observation()
    assert mgr.take_last_observation() is None, "stash must clear on read — no stale serve"
