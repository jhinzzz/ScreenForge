"""Tests for common/capabilities.py — capability payload structure."""

from common.capabilities import (
    ACTIONS_REQUIRING_EXTRA_VALUE,
    FEATURES_BY_PLATFORM,
    GLOBAL_ACTIONS,
    LOCATORS_BY_PLATFORM,
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


class TestLocatorMatrix:
    """The capabilities payload is the agent's machine-readable contract for
    which locator works where. These pin it to the real code behavior (T8)."""

    def test_payload_exposes_locators_and_features(self):
        payload = get_capabilities_payload()
        assert payload["locators"] == {p: list(v) for p, v in LOCATORS_BY_PLATFORM.items()}
        assert payload["features"] == {f: list(v) for f, v in FEATURES_BY_PLATFORM.items()}

    def test_every_platform_has_a_locator_list(self):
        payload = get_capabilities_payload()
        for platform in SUPPORTED_PLATFORMS:
            assert platform in payload["locators"]
            assert payload["locators"][platform], f"{platform} has no locators"

    def test_ref_and_bbox_are_web_only(self):
        # Matches reality: utils_xml / utils_ios emit no ref; executor visual
        # fallback is gated on web. Agents must not issue ref on mobile.
        assert "ref" in LOCATORS_BY_PLATFORM["web"]
        assert "ref" not in LOCATORS_BY_PLATFORM["android"]
        assert "ref" not in LOCATORS_BY_PLATFORM["ios"]
        assert FEATURES_BY_PLATFORM["ref_bbox"] == ["web"]
        assert FEATURES_BY_PLATFORM["visual_fallback"] == ["web"]

    def test_css_is_web_only(self):
        assert "css" in LOCATORS_BY_PLATFORM["web"]
        assert "css" not in LOCATORS_BY_PLATFORM["android"]
        assert "css" not in LOCATORS_BY_PLATFORM["ios"]

    def test_locator_values_are_known_types(self):
        known = {"css", "ref", "resourceId", "text", "description"}
        for platform, locs in LOCATORS_BY_PLATFORM.items():
            for loc in locs:
                assert loc in known, f"{platform} lists unknown locator {loc}"


class TestActionConstants:
    def test_global_actions_are_subset_of_supported(self):
        assert GLOBAL_ACTIONS.issubset(set(SUPPORTED_ACTIONS))

    def test_extra_value_actions_are_subset_of_supported(self):
        assert ACTIONS_REQUIRING_EXTRA_VALUE.issubset(set(SUPPORTED_ACTIONS))

    def test_goto_is_both_global_and_requires_extra(self):
        assert "goto" in GLOBAL_ACTIONS
        assert "goto" in ACTIONS_REQUIRING_EXTRA_VALUE
