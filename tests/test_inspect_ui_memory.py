"""inspect_ui carries last run's locator for the named task, at decision time.

The store and the lookup already existed — but the hit reached the agent in the
execute RESULT, i.e. after it had already chosen and acted. Here it rides the
payload the agent plans from. Not passing `task` keeps today's behavior exactly.
"""

import json

import cli.tool_protocol_handlers as tph
import config.config as config
from common.tool_protocol import ToolRequest

_TREE_JSON = '{"ui_elements":[{"text":"登录","id":"login-btn"}]}'


class _FakeAdapter:
    def take_screenshot(self):
        return b"png"

    def teardown(self):
        pass


def _seed_memory(tmp_path, monkeypatch):
    memory_path = tmp_path / "case_memory.json"
    memory_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-07-27T00:00:00",
                "entries": [
                    {
                        # memory_id has NO default on CaseMemoryEntry. Omit it and
                        # model_validate raises, load_document swallows it and
                        # returns an EMPTY store — the test then fails with a
                        # confusing empty `memory` instead of a schema error.
                        "memory_id": "android:action:dianji-denglu:abc1234567",
                        "platform": "android",
                        "control_kind": "action",
                        "control_label": "点击登录",
                        "source_ref": "",
                        "success_count": 3,
                        "last_used_at": "2026-07-27T00:00:00",
                        "successful_actions": ["click|resourceId|login-btn"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CASE_MEMORY_PATH", memory_path)


def _patch_capture(monkeypatch):
    monkeypatch.setattr(tph, "_connect_adapter", lambda args, reporter: _FakeAdapter())
    monkeypatch.setattr(
        tph,
        "_capture_ui_state",
        lambda args, adapter, reporter, step_index: (_TREE_JSON, None),
    )


def _request(**extra) -> ToolRequest:
    return ToolRequest.model_validate(
        {"operation": "inspect_ui", "platform": "android", **extra}
    )


def test_no_task_means_no_memory_lookup(monkeypatch, tmp_path):
    _seed_memory(tmp_path, monkeypatch)
    _patch_capture(monkeypatch)
    payload = tph.build_inspect_ui_payload(_request())
    assert payload["memory"] == {}


def test_matching_task_returns_the_entry(monkeypatch, tmp_path):
    _seed_memory(tmp_path, monkeypatch)
    _patch_capture(monkeypatch)
    payload = tph.build_inspect_ui_payload(_request(task="点击登录"))
    assert payload["memory"]["control_label"] == "点击登录"
    assert payload["memory"]["successful_actions"] == ["click|resourceId|login-btn"]


def test_unknown_task_returns_empty_memory(monkeypatch, tmp_path):
    _seed_memory(tmp_path, monkeypatch)
    _patch_capture(monkeypatch)
    payload = tph.build_inspect_ui_payload(_request(task="从未见过的任务"))
    assert payload["memory"] == {}


def test_wrong_platform_does_not_match(monkeypatch, tmp_path):
    _seed_memory(tmp_path, monkeypatch)
    _patch_capture(monkeypatch)
    payload = tph.build_inspect_ui_payload(
        ToolRequest.model_validate(
            {"operation": "inspect_ui", "platform": "web", "task": "点击登录"}
        )
    )
    assert payload["memory"] == {}


def test_memory_read_failure_does_not_break_inspect(monkeypatch, tmp_path):
    _seed_memory(tmp_path, monkeypatch)
    _patch_capture(monkeypatch)

    class _Boom:
        def find_entry(self, **kwargs):
            raise OSError("disk gone")

    monkeypatch.setattr(tph, "_load_case_memory_store", lambda: _Boom())
    payload = tph.build_inspect_ui_payload(_request(task="点击登录"))
    # A hint failing must never cost the agent its UI tree.
    assert payload["ok"] is True
    assert payload["memory"] == {}
    assert payload["element_count"] == 1
