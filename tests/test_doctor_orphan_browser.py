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
        assert result["pid"] == 4242
        assert "4242" in result["error"]
        assert "web-stop" in result["hint"]


class TestOrphanBrowserPreflightWiring:
    def test_web_preflight_includes_orphan_check(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web_adapter, "_read_session", lambda: None)
        result = preflight.run_preflight("web", tmp_path, tmp_path)
        names = [c.get("name") for c in result["checks"]]
        assert "orphan_web_browser" in names

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
            "orphan_web_browser", "Leaked persistent Chromium still running (pid 4242)"
        )
        assert remediation["fix_command"] == "screenforge --web-stop"
        assert "web-stop" in remediation["fix_label"].lower() or "Chromium" in remediation["fix_label"]

    def test_summary_surfaces_recommendation(self):
        checks = [
            {
                "name": "orphan_web_browser",
                "ok": False,
                "error": "Leaked persistent Chromium still running (pid 4242, http://127.0.0.1:9333)",
                "hint": "Run `screenforge --web-stop` to terminate the leftover persistent browser.",
            }
        ]
        summary = _build_doctor_summary(checks)
        assert summary["ok"] is False
        actions = summary["recommended_actions"]
        assert any(a.get("fix_command") == "screenforge --web-stop" for a in actions)

    def test_cleanup_sorts_after_real_blockers(self):
        # A genuine config blocker must rank ahead of the cleanup advisory.
        checks = [
            {
                "name": "orphan_web_browser",
                "ok": False,
                "error": "Leaked persistent Chromium still running (pid 4242)",
                "hint": "Run `screenforge --web-stop` to terminate the leftover persistent browser.",
            },
            {"name": "config", "ok": False, "errors": ["OPENAI_API_KEY 未配置"]},
        ]
        summary = _build_doctor_summary(checks)
        categories = [g["category"] for g in summary["groups"]]
        assert categories.index("config") < categories.index("cleanup")
