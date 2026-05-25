"""Interactive init wizard: guides new users through first-time setup."""

from pathlib import Path


def _prompt_choice(question: str, options: list[str], default: int = 0) -> int:
    print(f"\n  {question}")
    for i, opt in enumerate(options):
        marker = ">" if i == default else " "
        print(f"  {marker} [{i + 1}] {opt}")
    while True:
        raw = input(f"  Choice [{default + 1}]: ").strip()
        if not raw:
            return default
        try:
            choice = int(raw) - 1
            if 0 <= choice < len(options):
                return choice
        except ValueError:
            pass
        print(f"  Please enter 1-{len(options)}")


def _prompt_input(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"  {question}{suffix}: ").strip()
    return raw or default


def run_init_mode() -> int:
    print("\n  screenforge init — First-time setup wizard")
    print("  " + "=" * 44)

    # Step 1: Platform
    platform_idx = _prompt_choice(
        "Which platform will you test?",
        ["Web (Chrome/Playwright)", "Android (uiautomator2)", "iOS (WebDriverAgent)"],
        default=0,
    )
    platform = ["web", "android", "ios"][platform_idx]

    # Step 2: LLM config
    print("\n  ScreenForge needs an LLM API key for AI-driven testing.")
    print("  (Skip this for --demo mode which requires no key)")

    api_key = _prompt_input("OPENAI_API_KEY (or compatible)", "sk-...")
    base_url = _prompt_input("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = _prompt_input("MODEL_NAME", "gpt-4o")

    # Step 3: Write .env
    env_path = Path(".env")
    if env_path.exists():
        overwrite = _prompt_choice(
            ".env already exists. Overwrite?",
            ["No, keep existing", "Yes, overwrite"],
            default=0,
        )
        if overwrite == 0:
            print("  Keeping existing .env")
        else:
            _write_env(env_path, api_key, base_url, model)
    else:
        _write_env(env_path, api_key, base_url, model)

    # Step 4: Platform-specific checks
    print(f"\n  Platform: {platform}")
    if platform == "web":
        _check_web_deps()
    elif platform == "android":
        _check_android_deps()
    elif platform == "ios":
        _check_ios_deps()

    # Step 5: Suggest next steps
    print("\n  Setup complete! Next steps:")
    print("  " + "-" * 30)
    print("  1. screenforge --demo                    # See it work (no API key needed)")
    print(f"  2. screenforge --doctor --platform {platform}  # Verify environment")
    print(f"  3. screenforge --action goto --platform {platform} --extra-value \"https://example.com\"")
    print()

    return 0


def _write_env(path: Path, api_key: str, base_url: str, model: str) -> None:
    content = f"""OPENAI_API_KEY = "{api_key}"
OPENAI_BASE_URL = "{base_url}"
MODEL_NAME = "{model}"
"""
    path.write_text(content)
    print(f"  Written: {path}")


def _check_web_deps() -> None:
    try:
        import playwright  # noqa: F401
        print("  [ok] playwright installed")
    except ImportError:
        print("  [!!] playwright not installed")
        print("       Fix: pip install playwright && playwright install chromium")
        return

    from shutil import which
    if which("chromium") or which("google-chrome") or which("chrome"):
        print("  [ok] Chrome/Chromium found")
    else:
        print("  [ok] Will use Playwright's bundled Chromium")


def _check_android_deps() -> None:
    from shutil import which

    if which("adb"):
        print("  [ok] adb found")
    else:
        print("  [!!] adb not found in PATH")
        print("       Fix: install Android SDK platform-tools")

    try:
        import uiautomator2  # noqa: F401
        print("  [ok] uiautomator2 installed")
    except ImportError:
        print("  [!!] uiautomator2 not installed")
        print("       Fix: pip install screenforge[android]")


def _check_ios_deps() -> None:
    try:
        import wda  # noqa: F401
        print("  [ok] facebook-wda installed")
    except ImportError:
        print("  [!!] facebook-wda not installed")
        print("       Fix: pip install screenforge[ios]")
