"""The action payloads must compose common/observation.py without changing shape.

Task 2 is a pure refactor: same keys, same values. These tests pin the two
things a careless refactor breaks — the assertion_failed branch staying a bare
verdict, and element_count still agreeing with the tree.
"""

from cli.modes.action import build_failure_payload, build_success_payload

_TREE = {"ui_elements": [{"text": "登录"}, {"text": "注册"}]}


def test_success_payload_keys_unchanged():
    payload = build_success_payload(
        action_name="click_login",
        platform="android",
        ui_tree=_TREE,
        current_url="",
        output_script="test_cases/android/test_x.py",
    )
    assert set(payload) == {
        "ok", "action", "platform", "ui_tree", "element_count",
        "output_script", "current_url",
    }
    assert payload["element_count"] == 2
    assert payload["ok"] is True


def test_engine_error_carries_tree_and_count():
    payload = build_failure_payload(
        action_name="click_login",
        platform="android",
        assertion_failed=False,
        error_code="E030",
        locator_value="登陆",
        ui_tree=_TREE,
        current_url="",
    )
    assert payload["result"] == "engine_error"
    assert payload["element_count"] == 2
    assert payload["ui_tree"] == _TREE


def test_assertion_failed_stays_a_bare_verdict():
    # A failed assertion is a verdict, not a locate problem: no tree, no count,
    # no candidates, no retry bait. Refactoring must not leak them in.
    payload = build_failure_payload(
        action_name="assert_login",
        platform="android",
        assertion_failed=True,
        error_code="E036",
        locator_value="欢迎",
        ui_tree=_TREE,
        current_url="",
    )
    assert payload["result"] == "assertion_failed"
    assert "ui_tree" not in payload
    assert "element_count" not in payload
    assert "candidates" not in payload
