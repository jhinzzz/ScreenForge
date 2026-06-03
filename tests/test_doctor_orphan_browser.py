"""Doctor check for the leaked persistent Chromium (backlog #1).

The web adapter launches Chromium detached on port 9333 and keeps it alive
across CLI calls so later runs can reconnect; `--web-stop` reaps it. Doctor
previously had no way to *notice* a leftover one. These tests pin the new
`orphan_web_browser` check and its wiring through the doctor summary so the
recommendation ("run `screenforge --web-stop`") actually reaches the user.

All hermetic — the session file and pid liveness are mocked, no real browser.
"""

import common.preflight as preflight
from cli.doctor import (
    _build_doctor_remediation,
    _build_doctor_summary,
    _classify_doctor_check,
)
from common.adapters import web_adapter


class TestOrphanBrowserCheck:
    def test_no_session_file_is_ok(self, monkeypatch):
        monkeypatch.setattr(web_adapter, "_read_session", lambda: None)
        result = preflight.check_orphan_web_browser()
        assert result["name"] == "orphan_web_browser"
        assert result["ok"] is True

    def test_dead_pid_is_ok(self, monkeypatch):
        # A recorded-but-dead browser is not a leak to report; --web-stop / the
        # reconnect path already clear stale sessions.
        monkeypatch.setattr(web_adapter, "_read_session", lambda: {"pid": 4242, "cdp_url": "http://127.0.0.1:9333"})
        monkeypatch.setattr(web_adapter, "_is_process_alive", lambda pid: False)
        assert preflight.check_orphan_web_browser()["ok"] is True

    def test_missing_pid_is_ok(self, monkeypatch):
        monkeypatch.setattr(web_adapter, "_read_session", lambda: {"cdp_url": "http://127.0.0.1:9333"})
        assert preflight.check_orphan_web_browser()["ok"] is True

    def test_live_pid_is_flagged(self, monkeypatch):
        monkeypatch.setattr(
            web_adapter, "_read_session", lambda: {"pid": 4242, "cdp_url": "http://127.0.0.1:9333"}
        )
        monkeypatch.setattr(web_adapter, "_is_process_alive", lambda pid: True)
        result = preflight.check_orphan_web_browser()
        assert result["ok"] is False
        # Advisory: a live persistent browser is the intended reconnect target,
        # not a hard fault — it must be tagged so run_preflight excludes it from
        # the pass/fail aggregate.
        assert result["advisory"] is True
        assert result["pid"] == 4242
        assert "4242" in result["error"]
        assert "web-stop" in result["hint"]

    def test_clean_result_is_advisory_tagged(self, monkeypatch):
        # Even the ok=True path carries advisory=True so callers can treat the
        # check uniformly.
        monkeypatch.setattr(web_adapter, "_read_session", lambda: None)
        result = preflight.check_orphan_web_browser()
        assert result["ok"] is True
        assert result["advisory"] is True


class TestOrphanBrowserPreflightWiring:
    def test_web_preflight_includes_orphan_check(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web_adapter, "_read_session", lambda: None)
        result = preflight.run_preflight("web", tmp_path, tmp_path)
        names = [c.get("name") for c in result["checks"]]
        assert "orphan_web_browser" in names

    def test_live_browser_does_not_fail_preflight(self, tmp_path, monkeypatch):
        # The whole point of the advisory fix: a live persistent browser is the
        # normal web steady state and must NOT flip run_preflight's ok verdict.
        # (Other web checks short-circuit when the CDP endpoint is down, so the
        # only non-ok check here is the advisory one.)
        monkeypatch.setattr(
            web_adapter, "_read_session", lambda: {"pid": 4242, "cdp_url": "http://127.0.0.1:9333"}
        )
        monkeypatch.setattr(web_adapter, "_is_process_alive", lambda pid: True)
        result = preflight.run_preflight("web", tmp_path, tmp_path)
        orphan = next(c for c in result["checks"] if c["name"] == "orphan_web_browser")
        assert orphan["ok"] is False  # the advisory finding fired
        # ...but it did not drag the overall verdict down.
        non_advisory_ok = all(
            c.get("ok", False) for c in result["checks"] if not c.get("advisory", False)
        )
        assert result["ok"] == non_advisory_ok

    def test_non_web_preflight_skips_orphan_check(self, tmp_path, monkeypatch):
        # The check is web-only — it must not appear for android/ios.
        monkeypatch.setattr(web_adapter, "_read_session", lambda: {"pid": 4242})
        monkeypatch.setattr(web_adapter, "_is_process_alive", lambda pid: True)
        result = preflight.run_preflight("android", tmp_path, tmp_path)
        names = [c.get("name") for c in result["checks"]]
        assert "orphan_web_browser" not in names


class TestOrphanBrowserDoctorWiring:
    def test_classified_as_low_priority_cleanup(self):
        meta = _classify_doctor_check({"name": "orphan_web_browser"})
        assert meta["category"] == "cleanup"
        # Sorts after every real blocker (config=1 .. connectivity=4).
        assert meta["priority"] == 5

    def test_remediation_points_at_web_stop(self):
        remediation = _build_doctor_remediation(
            "orphan_web_browser", "Persistent Chromium still running (pid 4242)"
        )
        assert remediation["fix_command"] == "screenforge --web-stop"
        assert "web-stop" in remediation["fix_label"].lower() or "Chromium" in remediation["fix_label"]

    def test_advisory_surfaces_as_note_not_failure(self):
        # An advisory orphan finding must land in summary["advisories"] (a NOTE)
        # and must NOT flip summary["ok"] or appear among recommended_actions.
        checks = [
            {
                "name": "orphan_web_browser",
                "ok": False,
                "advisory": True,
                "error": "Persistent Chromium still running (pid 4242, http://127.0.0.1:9333)",
                "hint": "Run `screenforge --web-stop` to reclaim it (this is a note, not a failure).",
            }
        ]
        summary = _build_doctor_summary(checks)
        assert summary["ok"] is True, "advisory finding wrongly failed the summary"
        assert summary["recommended_actions"] == []
        advisories = summary["advisories"]
        assert any(a.get("fix_command") == "screenforge --web-stop" for a in advisories)

    def test_advisory_does_not_displace_real_blocker_verdict(self):
        # A genuine config blocker fails the summary; the advisory rides along
        # as a note without joining the failure groups.
        checks = [
            {
                "name": "orphan_web_browser",
                "ok": False,
                "advisory": True,
                "error": "Persistent Chromium still running (pid 4242)",
                "hint": "Run `screenforge --web-stop` to reclaim it.",
            },
            {"name": "config", "ok": False, "errors": ["OPENAI_API_KEY missing"]},
        ]
        summary = _build_doctor_summary(checks)
        assert summary["ok"] is False  # the real blocker fails it
        categories = [g["category"] for g in summary["groups"]]
        assert "config" in categories
        assert "cleanup" not in categories  # advisory never becomes a failure group
        assert len(summary["advisories"]) == 1
