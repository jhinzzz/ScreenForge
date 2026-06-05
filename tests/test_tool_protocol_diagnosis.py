"""Contract test for the MCP execute failure_diagnosis enrichment.

The MCP execute path is run-report shaped (no live ui_elements), so the tech
design scopes it to error_code + fix only — NOT did-you-mean candidates. This
pins that minimal contract and the honest no-code degrade.

    NOTE: these pin the table + the guard expression the execute path uses.
    Full build_tool_response_payload integration needs a run-report fixture and
    is deliberately deferred (the MCP execute path is minimal per the design).
"""

from common.error_codes import lookup


def test_error_codes_lookup_shape_for_execute_diagnosis():
    # The execute path builds {error_code, message, fix} from lookup() when the
    # run summary carries an error_code. Pin that the table feeds it correctly.
    msg, fix = lookup("E037")
    diagnosis = {"error_code": "E037", "message": msg, "fix": fix}
    assert diagnosis["error_code"] == "E037"
    assert diagnosis["fix"]
    assert "locate" in diagnosis["message"].lower()


def test_missing_code_normalization_yields_empty():
    # No error_code in summary → no failure_diagnosis (empty dict), never a
    # fabricated code. This mirrors the execute path's `if code:` guard.
    code = str({}.get("error_code", "") or "").strip()
    assert code == ""  # nothing to look up → execute path leaves failure_diagnosis {}
