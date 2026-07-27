"""Mobile elements carry `id` (resourceId) but no `ref` — suggest the id.

utils/utils_xml.py emits class/text/desc/id and no ref, so the ref branch
correctly skips on Android; before this fix the code then fell straight to
text and NEVER suggested resourceId, despite resourceId outranking text in
the repo's own locator law. Web tests can't catch it: compress_web_dom always
supplies a ref.

Probe values are chosen to clear CANDIDATE_THRESHOLD = 0.55 (measured:
"登录按钮"/"登录" = 0.667, "返回按钮"/"返回按键" = 0.750). Do NOT swap in the
tempting typo "登陆" — it scores 0.500 against "登录", yields zero candidates,
and turns these into vacuous assertions on an empty list.
"""

from common.failure_diagnosis import diagnose


def _android_page():
    return [
        {"class": "Button", "text": "登录", "id": "com.app:id/login_btn"},
        {"class": "Button", "text": "注册", "id": "com.app:id/reg_btn"},
    ]


def _web_page():
    return [{"class": "button", "text": "登录", "ref": "@7", "id": "login"}]


def test_android_candidate_suggests_resource_id():
    diag = diagnose(error_code="E030", locator_value="登录按钮", ui_elements=_android_page())
    assert diag.candidates
    top = diag.candidates[0]
    assert top.locator == {"type": "resourceId", "value": "com.app:id/login_btn"}


def test_web_candidate_still_prefers_ref_over_id():
    diag = diagnose(error_code="E030", locator_value="登录按钮", ui_elements=_web_page())
    assert diag.candidates[0].locator == {"type": "ref", "value": "@7"}


def test_element_without_ref_or_id_falls_back_to_text():
    diag = diagnose(
        error_code="E030",
        locator_value="登录按钮",
        ui_elements=[{"class": "Button", "text": "登录"}],
    )
    assert diag.candidates[0].locator == {"type": "text", "value": "登录"}


def test_description_match_without_ids_uses_description():
    diag = diagnose(
        error_code="E030",
        locator_value="返回按钮",
        ui_elements=[{"class": "ImageButton", "desc": "返回按键"}],
    )
    assert diag.candidates[0].locator["type"] == "description"


def test_recommended_next_step_uses_the_resource_id():
    diag = diagnose(error_code="E030", locator_value="登录按钮", ui_elements=_android_page())
    assert diag.recommended_next_step["action"] == "retry_with_candidate"
    assert diag.recommended_next_step["locator"]["type"] == "resourceId"
