"""Inline actions must not all collapse into one case-memory entry.

Every inline `--action` run writes the same sentinel `source_ref`
("inline://action"), and both the upsert and the lookup matched `source_ref`
BEFORE `control_label`. So the first inline action recorded on a platform
absorbed every later one: `--action-name "点击登录"` bumped the counter on the
pre-existing `swipe:up` entry instead of creating its own, and `task="点击登录"`
could never hit. The sentinel is provenance for reports, never an identity.
"""

import tempfile
from pathlib import Path

from common.case_memory import CaseMemoryStore

_SENTINEL = "inline://action"


def _store() -> CaseMemoryStore:
    return CaseMemoryStore(file_path=Path(tempfile.mkdtemp()) / "case_memory.json")


def _run(store: CaseMemoryStore, label: str, source_ref: str = _SENTINEL) -> None:
    store.upsert_from_run(
        summary={
            "execution_mode": "run",
            "platform": "android",
            "status": "success",
            "run_id": "r1",
            "finished_at": "2026-07-27T20:00:00",
            "control_summary": {
                "control_kind": "action",
                "control_label": label,
                "source_ref": source_ref,
            },
        },
        step_records=[],
    )


def test_distinct_action_labels_get_distinct_entries():
    store = _store()
    _run(store, "swipe:up")
    _run(store, "点击登录")
    labels = sorted(e.control_label for e in store.load_document().entries)
    assert labels == ["swipe:up", "点击登录"]


def test_repeating_the_same_label_still_updates_one_entry():
    store = _store()
    _run(store, "swipe:up")
    _run(store, "swipe:up")
    entries = store.load_document().entries
    assert len(entries) == 1
    assert entries[0].success_count == 2


def test_named_action_is_findable_by_its_label():
    store = _store()
    _run(store, "swipe:up")
    _run(store, "点击登录")
    hit = store.find_entry(
        platform="android", control_kind="action", control_label="点击登录"
    )
    assert hit is not None
    assert hit["control_label"] == "点击登录"


def test_sentinel_source_ref_never_matches_a_different_label():
    # The bug's read half: a lookup carrying the sentinel returned whichever
    # inline entry came first, regardless of the label asked for.
    store = _store()
    _run(store, "swipe:up")
    assert (
        store.find_entry(
            platform="android",
            control_kind="action",
            control_label="点击登录",
            source_ref=_SENTINEL,
        )
        is None
    )


def test_real_source_ref_still_identifies_across_a_rename():
    # Workflows carry a real path: renaming the workflow must not orphan its
    # history. This is the behavior the sentinel was free-riding on.
    store = _store()
    _run(store, "old_name", source_ref="/tmp/flow.yaml")
    _run(store, "new_name", source_ref="/tmp/flow.yaml")
    entries = store.load_document().entries
    assert len(entries) == 1
    assert entries[0].success_count == 2
