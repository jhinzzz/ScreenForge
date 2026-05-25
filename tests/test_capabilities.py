"""Tests for common/capabilities.py — capability payload structure."""

from common.capabilities import (
    ACTIONS_REQUIRING_EXTRA_VALUE,
    GLOBAL_ACTIONS,
    SUPPORTED_ACTIONS,
    SUPPORTED_PLATFORMS,
    get_capabilities_payload,
)


class TestCapabilitiesPayload:
    def test_contains_required_keys(self):
        payload = get_capabilities_payload()
        assert "platforms" in payload
        assert "execution_modes" in payload
        assert "supported_actions" in payload
        assert "supports" in payload
        assert "docs" in payload

    def test_platforms_match_constant(self):
        payload = get_capabilities_payload()
        assert payload["platforms"] == list(SUPPORTED_PLATFORMS)

    def test_actions_match_constant(self):
        payload = get_capabilities_payload()
        assert payload["supported_actions"] == list(SUPPORTED_ACTIONS)

    def test_global_actions_sorted(self):
        payload = get_capabilities_payload()
        assert payload["global_actions"] == ["goto", "press", "swipe"]

    def test_supports_has_core_features(self):
        payload = get_capabilities_payload()
        supports = payload["supports"]
        assert supports["doctor"] is True
        assert supports["resume"] is True
        assert supports["mcp_server"] is True
        assert supports["inspect_ui"] is True

    def test_docs_paths_are_strings(self):
        payload = get_capabilities_payload()
        for key, val in payload["docs"].items():
            assert isinstance(val, str)
            assert val.endswith(".md")


class TestActionConstants:
    def test_global_actions_are_subset_of_supported(self):
        assert GLOBAL_ACTIONS.issubset(set(SUPPORTED_ACTIONS))

    def test_extra_value_actions_are_subset_of_supported(self):
        assert ACTIONS_REQUIRING_EXTRA_VALUE.issubset(set(SUPPORTED_ACTIONS))

    def test_goto_is_both_global_and_requires_extra(self):
        assert "goto" in GLOBAL_ACTIONS
        assert "goto" in ACTIONS_REQUIRING_EXTRA_VALUE
