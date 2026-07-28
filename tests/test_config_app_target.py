"""APP_ENV_CONFIG must be env-driven, not a hardcoded dict.

A pip-installed user can't edit site-packages to set an auto-launch target, so
the values come from APP_TARGET_<ENV>_<PLATFORM> env vars. Empty (the default)
means "don't auto-launch".
"""

import importlib


def test_app_target_reads_env(monkeypatch):
    monkeypatch.setenv("APP_TARGET_DEV_ANDROID", "com.example.app")
    monkeypatch.setenv("APP_TARGET_PROD_WEB", "https://example.com")

    import config.config as config
    importlib.reload(config)
    try:
        assert config.APP_ENV_CONFIG["dev"]["android"] == "com.example.app"
        assert config.APP_ENV_CONFIG["prod"]["web"] == "https://example.com"
        # Unset targets stay empty → launch_app early-returns (no auto-launch).
        assert config.APP_ENV_CONFIG["dev"]["ios"] == ""
    finally:
        importlib.reload(config)  # restore module-level state for other tests
