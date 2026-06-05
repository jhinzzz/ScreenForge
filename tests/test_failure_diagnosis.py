"""Tests for common/failure_diagnosis.py — did-you-mean candidate ranking.

Pure function, no device/page. Pins the honesty contract: below-threshold
similarity yields NO candidates (we never fabricate a misleading suggestion),
and the assertion_failed path carries no candidates or next-step (a failed
assertion is a verdict, not a locate problem).
"""

from common.failure_diagnosis import (
    CANDIDATE_THRESHOLD,
    diagnose,
)

# Mimics utils_web.py element shape: ref/text/desc/name/clickable.
_ELEMENTS = [
    {"ref": "@1", "class": "a", "text": "Log in", "clickable": True},
    {"ref": "@2", "class": "button", "text": "Login now", "clickable": True},
    {"ref": "@3", "class": "div", "text": "Forgot password?", "clickable": True},
    {"ref": "@4", "class": "footer", "text": "Privacy policy", "clickable": True},
]


def test_did_you_mean_ranks_closest_first():
    diag = diagnose(error_code="E037", locator_value="Login", ui_elements=_ELEMENTS)
    assert diag.candidates, "expected at least one candidate"
    # "Log in" (0.909) must outrank "Login now" (0.714); both clear the 0.55 bar.
    assert diag.candidates[0].text == "Log in"
    assert diag.candidates[0].score >= diag.candidates[1].score


def test_candidate_has_suggested_ref_locator():
    diag = diagnose(error_code="E037", locator_value="Login", ui_elements=_ELEMENTS)
    top = diag.candidates[0]
    assert top.locator == {"type": "ref", "value": "@1"}


def test_below_threshold_yields_no_candidates_no_fabrication():
    diag = diagnose(
        error_code="E037",
        locator_value="xyzzy_nonexistent_42",
        ui_elements=_ELEMENTS,
    )
    assert diag.candidates == []
    # Honest next-step: re-inspect, do not invent a target.
    assert diag.recommended_next_step["action"] == "re_inspect"


def test_assertion_failed_carries_no_candidates_or_nextstep():
    # "ASSERT" is deliberately NOT a real ERROR_CODES key — this also pins that
    # an unknown code degrades gracefully (generic fallback) while still
    # suppressing candidates on the assertion path.
    diag = diagnose(
        error_code="ASSERT",
        locator_value="Dashboard",
        ui_elements=_ELEMENTS,
        assertion_failed=True,
    )
    assert diag.candidates == []
    assert diag.recommended_next_step is None


def test_threshold_constant_is_conservative():
    # A guard so nobody silently loosens the bar and starts fabricating.
    assert 0.4 <= CANDIDATE_THRESHOLD <= 0.7


def test_locator_priority_text_when_no_ref():
    els = [{"class": "button", "text": "Submit", "clickable": True}]  # no ref (mobile-ish)
    diag = diagnose(error_code="E037", locator_value="Submti", ui_elements=els)
    assert diag.candidates
    assert diag.candidates[0].locator == {"type": "text", "value": "Submit"}


def test_empty_ui_elements_degrades_to_code_and_fix_only():
    diag = diagnose(error_code="E037", locator_value="Login", ui_elements=[])
    assert diag.error_code == "E037"
    assert diag.fix
    assert diag.candidates == []


def test_to_dict_drops_none_nextstep():
    diag = diagnose(
        error_code="ASSERT",
        locator_value="x",
        ui_elements=[],
        assertion_failed=True,
    )
    d = diag.to_dict()
    assert "recommended_next_step" not in d
    assert d["error_code"] == "ASSERT"


def test_fix_request_codes_recommend_fix_not_reinspect():
    # E031/E032/E035 are malformed requests; E038 = located but action failed.
    # None are helped by re-inspecting, so they must route to fix_request.
    for code in ("E031", "E032", "E035", "E038"):
        diag = diagnose(error_code=code, locator_value="anything", ui_elements=[])
        assert diag.recommended_next_step["action"] == "fix_request", code
