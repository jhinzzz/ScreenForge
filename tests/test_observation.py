"""Tests for common/observation.py — the single agent-facing envelope builder.

Every agent-facing payload composes this. A wrong field here reaches the agent's
eyes in every mode at once, so the invariants are pinned: element_count is
DERIVED (never passed in), and absent data is an honest empty, never a guess.
"""

from common.observation import build_observation


def test_derives_element_count_from_tree():
    obs = build_observation(ui_tree={"ui_elements": [{"text": "登录"}, {"text": "注册"}]})
    assert obs["element_count"] == 2


def test_empty_tree_yields_zero_count_and_empty_defaults():
    obs = build_observation(ui_tree={})
    assert obs["element_count"] == 0
    assert obs["current_url"] == ""
    assert obs["screenshot_base64"] == ""


def test_null_ui_elements_does_not_crash():
    # Invariant 2: a compressor that emitted an explicit null must not raise.
    obs = build_observation(ui_tree={"ui_elements": None})
    assert obs["element_count"] == 0


def test_exact_key_set_no_extras():
    # Invariant 3 guard: an unreviewed key added here reaches every mode at once.
    obs = build_observation(ui_tree={"ui_elements": []})
    assert set(obs) == {
        "ui_tree", "element_count", "current_url", "screenshot_base64", "memory",
    }


def test_passes_through_url_and_screenshot():
    obs = build_observation(
        ui_tree={"ui_elements": []}, current_url="https://x.test/a", screenshot_base64="QUJD"
    )
    assert obs["current_url"] == "https://x.test/a"
    assert obs["screenshot_base64"] == "QUJD"


def test_memory_defaults_to_empty_dict():
    # Invariant 2: no history is an honest empty, never a fabricated hint.
    obs = build_observation(ui_tree={"ui_elements": []})
    assert obs["memory"] == {}


def test_memory_passes_through():
    entry = {"control_label": "点击登录", "successful_actions": ["click|text|登录"]}
    obs = build_observation(ui_tree={"ui_elements": []}, memory=entry)
    assert obs["memory"] == entry


def test_memory_none_normalizes_to_empty_dict():
    obs = build_observation(ui_tree={"ui_elements": []}, memory=None)
    assert obs["memory"] == {}
