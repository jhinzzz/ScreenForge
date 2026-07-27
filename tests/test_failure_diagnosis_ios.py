"""iOS elements carry `label`/`name` and nothing else — match on them.

utils/utils_ios.py's compress_ios_source writes only type/label/name/value/
accessible/disabled: no `text`, no `desc`, no `id`, no `ref`. While _MATCH_FIELDS
was ("text", "desc", "name") the whole did-you-mean feature was dead on iOS —
and dead in the worst way, because the compressor drops `name` when it equals
`label`, so the ordinary control matched nothing while an odd one matched by its
internal identifier and got handed back as a `description` locator. That is the
wrong attribute: executor.py's ios_key_map sends description->label.

Threshold note: CANDIDATE_THRESHOLD = 0.55, and probes here are exact or near
matches so they clear it comfortably.
"""

from common.failure_diagnosis import diagnose, rank_candidates


def test_label_only_element_is_a_candidate():
    """The common iOS shape: label present, name suppressed as a duplicate."""
    diag = diagnose(
        error_code="E030",
        locator_value="登录",
        ui_elements=[{"type": "Button", "label": "登录"}],
    )
    assert diag.candidates
    assert diag.candidates[0].locator == {"type": "description", "value": "登录"}


def test_label_match_wins_over_name_and_maps_to_label_lookup():
    """A label match must not be reported as resourceId — that would query `name`."""
    diag = diagnose(
        error_code="E030",
        locator_value="登录",
        ui_elements=[{"type": "Button", "label": "登录", "name": "loginBtn"}],
    )
    assert diag.candidates[0].locator == {"type": "description", "value": "登录"}


def test_name_match_maps_to_resource_id_not_description():
    """`name` is iOS's identifier: resourceId->name in executor's ios_key_map."""
    diag = diagnose(
        error_code="E030",
        locator_value="loginBtn",
        ui_elements=[{"type": "Button", "label": "Sign in", "name": "loginBtn"}],
    )
    assert diag.candidates[0].locator == {"type": "resourceId", "value": "loginBtn"}


def test_forward_lookup_also_sees_ios_labels():
    """rank_candidates() shares the matcher, so `intent` works on iOS too."""
    hits = rank_candidates("登录", [{"type": "Button", "label": "登录"}])
    assert [h["locator"] for h in hits] == [{"type": "description", "value": "登录"}]


def test_web_name_attribute_still_yields_ref():
    """Adding `label` must not disturb web: ref outranks every text field."""
    diag = diagnose(
        error_code="E030",
        locator_value="username",
        ui_elements=[{"class": "input", "name": "username", "ref": "@3", "id": "user"}],
    )
    assert diag.candidates[0].locator == {"type": "ref", "value": "@3"}
