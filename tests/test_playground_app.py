"""Tests for playground/app.py — the /api/step sink endpoint + time-travel seed.

Pins arch#2 (bounded memory: base64 never enters _step_log; LRU caps), the run
namespace isolation, and the G6 seed read endpoint contract. Uses FastAPI
TestClient (no live server). Skips cleanly if the playground extra isn't installed.
"""

import importlib

import pytest

pytest.importorskip("fastapi", reason="playground extra not installed (pip install screenforge[playground])")

from fastapi.testclient import TestClient  # noqa: E402

import playground.app as app_module  # noqa: E402


@pytest.fixture
def client():
    """Fresh in-memory state per test so LRU/isolation assertions don't bleed."""
    importlib.reload(app_module)
    app_module._step_log.clear()
    app_module._screenshot_b64 = ""
    return TestClient(app_module.app)


def _step_body(run_id="r1", step_index=1, b64=""):
    return {
        "run_id": run_id,
        "step_index": step_index,
        "code_lines": ["    with allure.step('x'):\n", "        d.click()\n"],
        "action_description": "x",
        "action": "click",
        "locator_type": "text",
        "locator_value": "登录",
        "extra_value": "",
        "success": True,
        "screenshot_b64": b64,
    }


class TestPostStep:
    """#7 — POST /api/step accumulates metadata; base64 stays out of _step_log."""

    def test_step_accumulates_metadata(self, client):
        resp = client.post("/api/step", json=_step_body(run_id="r1", step_index=1))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "r1" in app_module._step_log
        assert len(app_module._step_log["r1"]) == 1
        assert app_module._step_log["r1"][0]["action"] == "click"

    def test_base64_not_stored_in_step_log(self, client):
        big_b64 = "QQ==" * 1000
        client.post("/api/step", json=_step_body(run_id="r1", b64=big_b64))
        stored = app_module._step_log["r1"][0]
        # arch#2: the base64 frame must NOT be retained in the per-run log.
        assert "screenshot_b64" not in stored or not stored["screenshot_b64"]
        # …but it DID update the single live-frame slot.
        assert app_module._screenshot_b64 == big_b64

    def test_step_without_screenshot_leaves_slot_untouched(self, client):
        app_module._screenshot_b64 = "PREVIOUS"
        client.post("/api/step", json=_step_body(run_id="r1", b64=""))
        assert app_module._screenshot_b64 == "PREVIOUS"

    def test_multiple_steps_ordered(self, client):
        for i in range(1, 4):
            client.post("/api/step", json=_step_body(run_id="r1", step_index=i))
        steps = app_module._step_log["r1"]
        assert [s["step_index"] for s in steps] == [1, 2, 3]

    def test_duplicate_step_index_overwrites_last_writer_wins(self, client):
        """HIGH-2 guard: a failed/retried session step can re-push the same index.
        The seed indexes by step_index, so a dup must overwrite, not append a
        second ambiguous frame."""
        b1 = _step_body(run_id="r1", step_index=1)
        b1["action_description"] = "first attempt (failed)"
        client.post("/api/step", json=b1)
        b1b = _step_body(run_id="r1", step_index=1)
        b1b["action_description"] = "retry (ok)"
        client.post("/api/step", json=b1b)
        client.post("/api/step", json=_step_body(run_id="r1", step_index=2))
        steps = app_module._step_log["r1"]
        # exactly one frame per index, retry won
        assert [s["step_index"] for s in steps] == [1, 2]
        assert steps[0]["action_description"] == "retry (ok)"


class TestSeedEndpoint:
    """#8 — GET /api/run/{run_id}/steps: the time-travel seed read contract."""

    def test_returns_ordered_steps(self, client):
        for i in range(1, 4):
            client.post("/api/step", json=_step_body(run_id="run-A", step_index=i))
        resp = client.get("/api/run/run-A/steps")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "run-A"
        assert [s["step_index"] for s in body["steps"]] == [1, 2, 3]

    def test_unknown_run_returns_empty(self, client):
        resp = client.get("/api/run/does-not-exist/steps")
        assert resp.status_code == 200
        assert resp.json() == {"run_id": "does-not-exist", "steps": []}


class TestRunIsolation:
    """#9 — concurrent run_ids are namespaced; no cross-talk."""

    def test_two_runs_do_not_bleed(self, client):
        client.post("/api/step", json=_step_body(run_id="r1", step_index=1))
        client.post("/api/step", json=_step_body(run_id="r2", step_index=1))
        client.post("/api/step", json=_step_body(run_id="r1", step_index=2))
        assert len(app_module._step_log["r1"]) == 2
        assert len(app_module._step_log["r2"]) == 1
        assert app_module._step_log["r2"][0]["step_index"] == 1


class TestLruBounds:
    """#15 — arch#2: memory is bounded by run count and per-run step count."""

    def test_run_count_capped_evicts_oldest(self, client):
        n = app_module._MAX_RUNS + 5
        for i in range(n):
            client.post("/api/step", json=_step_body(run_id=f"run-{i}", step_index=1))
        assert len(app_module._step_log) == app_module._MAX_RUNS
        # The five oldest runs were evicted.
        assert "run-0" not in app_module._step_log
        assert f"run-{n - 1}" in app_module._step_log

    def test_active_run_stays_warm(self, client):
        """LRU: re-touching a run keeps it from eviction even as new runs arrive."""
        client.post("/api/step", json=_step_body(run_id="keep", step_index=1))
        for i in range(app_module._MAX_RUNS):
            client.post("/api/step", json=_step_body(run_id=f"flood-{i}", step_index=1))
            # keep 'keep' warm by touching it each round
            client.post("/api/step", json=_step_body(run_id="keep", step_index=i + 2))
        assert "keep" in app_module._step_log

    def test_per_run_steps_capped(self, client):
        cap = app_module._MAX_STEPS_PER_RUN
        for i in range(1, cap + 11):
            client.post("/api/step", json=_step_body(run_id="big", step_index=i))
        steps = app_module._step_log["big"]
        assert len(steps) == cap
        # Head was truncated — the newest steps survive.
        assert steps[-1]["step_index"] == cap + 10
        assert steps[0]["step_index"] == 11
