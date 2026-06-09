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


class TestSseFanout:
    """The /api/step → SSE delivery path is the ONLY route to a browser, and it
    carries a subtle contract: the base64 frame is popped OUT of _step_log (arch#2
    bounded memory) yet RE-ATTACHED to the SSE payload so the live client still
    renders inline (this is the exact pop/re-attach that the mime-race fix hinges
    on). Pin it: the wire keeps the frame, the log does not."""

    def test_step_event_carries_b64_while_log_strips_it(self, client):
        import asyncio

        # Subscribe exactly like /api/events does (app.py:139-140).
        q: asyncio.Queue = asyncio.Queue()
        app_module._subscribers.append(q)
        try:
            big_b64 = "QQ==" * 500
            resp = client.post(
                "/api/step", json=_step_body(run_id="r1", step_index=1, b64=big_b64)
            )
            assert resp.status_code == 200
            event = q.get_nowait()  # the fan-out enqueued synchronously in post_step
        finally:
            app_module._subscribers.remove(q)

        # On the wire: a 'step' event WITH the full frame inline.
        assert event["type"] == "step"
        assert event["step_index"] == 1
        assert event["screenshot_b64"] == big_b64
        # In the log: the same step WITHOUT the frame (bounded memory).
        stored = app_module._step_log["r1"][0]
        assert not stored.get("screenshot_b64")
        # …but the live-frame slot did capture it for /api/screenshot backfill.
        assert app_module._screenshot_b64 == big_b64

    def test_screenshotless_step_event_still_fans_out(self, client):
        import asyncio

        q: asyncio.Queue = asyncio.Queue()
        app_module._subscribers.append(q)
        try:
            client.post("/api/step", json=_step_body(run_id="r1", step_index=1, b64=""))
            event = q.get_nowait()
        finally:
            app_module._subscribers.remove(q)
        assert event["type"] == "step"
        assert event["screenshot_b64"] == ""  # degrade: no frame, still delivered


class TestMalformedPayload:
    """The real sink always sends a valid PlaygroundStepEvent (step_index is a
    required field), so these pin CURRENT behavior on inputs the sink never emits
    — documenting the localhost-trust boundary as deliberate, not accidental."""

    def test_missing_step_index_buckets_under_none(self, client):
        # A body with no step_index lands as step_index=None. Two such bodies
        # collapse to one (None == None in the de-dup scan) — acceptable because
        # the sink never omits step_index; documented here so it's not a surprise.
        client.post("/api/step", json={"run_id": "r", "code_lines": ["a\n"]})
        client.post("/api/step", json={"run_id": "r", "code_lines": ["b\n"]})
        steps = app_module._step_log["r"]
        assert len(steps) == 1  # last-writer-wins on the None key
        assert steps[0]["code_lines"] == ["b\n"]

    def test_missing_run_id_falls_back_to_default_bucket(self, client):
        resp = client.post("/api/step", json={"step_index": 1, "code_lines": ["a\n"]})
        assert resp.status_code == 200
        assert "default" in app_module._step_log  # body.get("run_id", "default")


class TestEditorDetection:
    """GET /api/editors — PATH probe only; resolved binary path never leaves the server."""

    def test_lists_only_detected_editors(self, client, monkeypatch):
        # Only 'trae' and 'code' are on PATH → only those two surface, in pref order.
        present = {"trae": "/usr/local/bin/trae", "code": "/usr/local/bin/code"}
        monkeypatch.setattr(app_module.shutil, "which", lambda b: present.get(b))
        resp = client.get("/api/editors")
        assert resp.status_code == 200
        eds = resp.json()["editors"]
        assert [e["id"] for e in eds] == ["trae", "code"]  # preference order preserved
        # The resolved path must NOT be exposed to the client.
        assert all("_path" not in e and "path" not in e for e in eds)

    def test_empty_when_no_editor_on_path(self, client, monkeypatch):
        monkeypatch.setattr(app_module.shutil, "which", lambda b: None)
        assert client.get("/api/editors").json()["editors"] == []


class TestBuildOpenCommand:
    """_build_open_command — each editor family's argv shape (never a shell string)."""

    @pytest.mark.parametrize("style,expected", [
        ("goto", ["/x/ed", "-g", "/f.py:12"]),
        ("colon", ["/x/ed", "/f.py:12"]),
        ("line-flag", ["/x/ed", "--line", "12", "/f.py"]),
        ("plus", ["/x/ed", "+12", "/f.py"]),
    ])
    def test_argv_shapes(self, style, expected):
        ed = {"_path": "/x/ed", "_args": style}
        assert app_module._build_open_command(ed, "/f.py", 12) == expected


class TestOpenInEditor:
    """POST /api/open — safety guards + fallback. Popen is mocked: no real launch."""

    @pytest.fixture
    def only_trae(self, monkeypatch):
        monkeypatch.setattr(app_module.shutil, "which",
                            lambda b: "/usr/local/bin/trae" if b == "trae" else None)

    def test_rejects_missing_file(self, client, only_trae, monkeypatch):
        calls = []
        monkeypatch.setattr(app_module.subprocess, "Popen", lambda c: calls.append(c))
        resp = client.post("/api/open", json={
            "file_path": "/tmp/nope_does_not_exist_xyz.py", "line": 3, "editor": "trae"})
        assert resp.json()["ok"] is False
        assert "not found" in resp.json()["error"]
        assert calls == []  # never launched

    def test_path_injection_is_inert(self, client, only_trae, monkeypatch, tmp_path):
        # A shell-injection-shaped path is treated as a literal filename. It doesn't
        # exist as a file → rejected; and even if it did, Popen gets an argv LIST,
        # so the '; touch' is an arg, never a shell command.
        calls = []
        monkeypatch.setattr(app_module.subprocess, "Popen", lambda c: calls.append(c))
        resp = client.post("/api/open", json={
            "file_path": "/tmp/x.py; touch /tmp/PWNED", "line": 1, "editor": "trae"})
        assert resp.json()["ok"] is False
        assert calls == []

    def test_unknown_editor_falls_back_to_first_detected(self, client, only_trae, monkeypatch, tmp_path):
        f = tmp_path / "test_demo.py"
        f.write_text("# t\n")
        captured = {}
        monkeypatch.setattr(app_module.subprocess, "Popen",
                            lambda c: captured.setdefault("cmd", c))
        resp = client.post("/api/open", json={
            "file_path": str(f), "line": 5, "editor": "bogus_editor"})
        body = resp.json()
        assert body["ok"] is True
        assert body["editor"] == "trae"  # fell back to first detected
        # Launched with the VSCode-family goto shape, resolved abs path, as argv list.
        assert captured["cmd"] == ["/usr/local/bin/trae", "-g", f"{f}:5"]

    def test_no_editor_detected_returns_error(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(app_module.shutil, "which", lambda b: None)
        f = tmp_path / "t.py"
        f.write_text("x\n")
        resp = client.post("/api/open", json={"file_path": str(f), "line": 1})
        assert resp.json()["ok"] is False
        assert "no editor" in resp.json()["error"].lower()

    def test_bad_line_defaults_to_one(self, client, only_trae, monkeypatch, tmp_path):
        f = tmp_path / "t.py"
        f.write_text("x\n")
        captured = {}
        monkeypatch.setattr(app_module.subprocess, "Popen",
                            lambda c: captured.setdefault("cmd", c))
        resp = client.post("/api/open", json={
            "file_path": str(f), "line": "not-a-number", "editor": "trae"})
        assert resp.json()["ok"] is True
        assert captured["cmd"] == ["/usr/local/bin/trae", "-g", f"{f}:1"]
