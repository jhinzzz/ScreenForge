"""Did-you-mean diagnoser for failed locate/action attempts.

Pure function — no device, no page, no I/O. Given the failed locator_value and
the current page's ui_elements, rank the most similar elements (difflib, stdlib,
zero new deps) and propose a concrete next step. Honesty is the contract: below
threshold we return NO candidates rather than a misleading guess (the same
"rather skip than write .first" spirit the duplicate-disambiguation work set),
and the assertion path carries nothing — a failed assertion is a verdict, not a
locate problem.
"""

import difflib
from dataclasses import asdict, dataclass, field

from common.error_codes import lookup

CANDIDATE_THRESHOLD = 0.55  # difflib ratio floor; below this is not a candidate
MAX_CANDIDATES = 3

# Element text fields to match against, in locator-priority order. `ref` is web
# only; mobile elements omit it, so a text/description match is the fallback.
_MATCH_FIELDS = ("text", "desc", "name")


@dataclass
class Candidate:
    text: str
    score: float
    locator: dict


@dataclass
class FailureDiagnosis:
    error_code: str
    message: str
    fix: str
    candidates: list[Candidate] = field(default_factory=list)
    recommended_next_step: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.recommended_next_step is None:
            d.pop("recommended_next_step")
        return d


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _best_field(el: dict, target: str) -> tuple[float, str, str]:
    """Return (best_score, matched_text, matched_field) over an element's text fields."""
    best = (0.0, "", "")
    for fld in _MATCH_FIELDS:
        val = str(el.get(fld, "")).strip()
        if not val:
            continue
        score = _ratio(target, val)
        if score > best[0]:
            best = (score, val, fld)
    return best


def _suggested_locator(el: dict, matched_text: str, matched_field: str) -> dict:
    """Locator priority: ref (web) > text > description. Mirrors agent_guide."""
    ref = str(el.get("ref", "")).strip()
    if ref:
        return {"type": "ref", "value": ref}
    if matched_field == "text":
        return {"type": "text", "value": matched_text}
    return {"type": "description", "value": matched_text}


def _rank_candidates(locator_value: str, ui_elements: list[dict]) -> list[Candidate]:
    target = str(locator_value or "").strip()
    if not target:
        return []
    scored: list[Candidate] = []
    for el in ui_elements:
        score, matched_text, matched_field = _best_field(el, target)
        if score < CANDIDATE_THRESHOLD or not matched_text:
            continue
        scored.append(
            Candidate(
                text=matched_text,
                score=round(score, 3),
                locator=_suggested_locator(el, matched_text, matched_field),
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:MAX_CANDIDATES]


def _recommend(error_code: str, fix: str, candidates: list[Candidate]) -> dict:
    if candidates:
        top = candidates[0]
        return {
            "action": "retry_with_candidate",
            "hint": f"Try {top.locator['value']} ('{top.text}')",
            "locator": top.locator,
        }
    # Codes where the problem is the request or the element itself, not page
    # staleness: E031/E032/E035 are malformed requests; E038 means the element
    # WAS located but the action failed/blocked. Re-inspecting helps none of
    # these — return the code's own fix.
    if error_code in {"E031", "E032", "E035", "E038"}:
        return {"action": "fix_request", "hint": fix}
    # E030/E033/E037 and anything else with no candidate: target not locatable
    # on the current view — re-inspect.
    return {
        "action": "re_inspect",
        "hint": "Target not on the current page; scroll it into view or add --vision.",
    }


def diagnose(
    *,
    error_code: str,
    locator_value: str,
    ui_elements: list[dict],
    assertion_failed: bool = False,
) -> FailureDiagnosis:
    msg, fix = lookup(error_code)

    # A failed assertion is a verdict, not a locate problem: no candidates, no
    # next-step. (Defensive — the --action json branch also simply doesn't call
    # diagnose() on the assertion path. Belt and suspenders.)
    if assertion_failed:
        return FailureDiagnosis(error_code=error_code, message=msg, fix=fix)

    candidates = _rank_candidates(locator_value, ui_elements)
    return FailureDiagnosis(
        error_code=error_code,
        message=msg,
        fix=fix,
        candidates=candidates,
        recommended_next_step=_recommend(error_code, fix, candidates),
    )
