"""Demo mode — showcases ScreenForge's full flow without API key or device."""

import sys
import time

from cli._version import __version__

DEMO_SCENARIO = {
    "title": "Login Flow Test",
    "url": "https://demo.screenforge.dev",
    "steps": [
        {
            "description": "Navigate to login page",
            "action": "goto",
            "target": "https://demo.screenforge.dev/login",
            "ui_tree_snippet": (
                '<div id="app">\n'
                '  <nav>\n'
                '    <a href="/login">Sign In</a>\n'
                '    <a href="/register">Sign Up</a>\n'
                '  </nav>\n'
                '</div>'
            ),
            "generated_code": 'page.goto("https://demo.screenforge.dev/login")',
        },
        {
            "description": "Enter username",
            "action": "input",
            "target": "#email → 'user@example.com'",
            "ui_tree_snippet": (
                '<form id="login-form">\n'
                '  <input id="email" type="email" placeholder="Email" />\n'
                '  <input id="password" type="password" placeholder="Password" />\n'
                '  <button type="submit">Sign In</button>\n'
                '</form>'
            ),
            "generated_code": (
                'page.locator("#email").first.fill("user@example.com")'
            ),
        },
        {
            "description": "Enter password",
            "action": "input",
            "target": "#password → '••••••••'",
            "ui_tree_snippet": None,
            "generated_code": 'page.locator("#password").first.fill("password123")',
        },
        {
            "description": "Click sign in button",
            "action": "click",
            "target": "text='Sign In'",
            "ui_tree_snippet": None,
            "generated_code": "page.get_by_text('Sign In').first.click()",
        },
        {
            "description": "Verify dashboard loaded",
            "action": "assert_exist",
            "target": "text='Welcome back'",
            "ui_tree_snippet": (
                '<main>\n'
                '  <h1>Welcome back</h1>\n'
                '  <div class="dashboard">...</div>\n'
                '</main>'
            ),
            "generated_code": (
                'expect(page.get_by_text("Welcome back").first).to_be_visible()'
            ),
        },
    ],
}

PYTEST_OUTPUT = '''import allure
import pytest
from playwright.sync_api import Page, expect


@allure.feature("Authentication")
@allure.story("Login Flow")
class TestLogin:
    @allure.step("Navigate to login page")
    def test_login_success(self, page: Page):
        page.goto("https://demo.screenforge.dev/login")

        with allure.step("Enter credentials"):
            page.locator("#email").first.fill("user@example.com")
            page.locator("#password").first.fill("password123")

        with allure.step("Submit login form"):
            page.get_by_text('Sign In').first.click()

        with allure.step("Verify dashboard loaded"):
            expect(page.get_by_text("Welcome back").first).to_be_visible()
'''


def _print_slow(text: str, delay: float = 0.02) -> None:
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")


def _print_step_header(step_num: int, total: int, description: str) -> None:
    print(f"\n  [{step_num}/{total}] {description}")


def run_demo_mode() -> int:
    scenario = DEMO_SCENARIO
    steps = scenario["steps"]

    print()
    print(f"  screenforge v{__version__} — demo mode")
    print(f"  Scenario: {scenario['title']}")
    print(f"  Target:   {scenario['url']} (simulated)")
    print("  " + "-" * 50)
    time.sleep(0.5)

    print("\n  Connecting to browser...", end="")
    time.sleep(0.3)
    print(" OK (simulated)")

    for i, step in enumerate(steps, 1):
        _print_step_header(i, len(steps), step["description"])
        time.sleep(0.3)

        if step["ui_tree_snippet"]:
            print("    inspect_ui:")
            for line in step["ui_tree_snippet"].split("\n"):
                print(f"      {line}")
            time.sleep(0.2)

        print(f"    action: {step['action']} → {step['target']}")
        time.sleep(0.2)

        print(f"    codegen: {step['generated_code']}")
        time.sleep(0.3)

    print("\n  " + "-" * 50)
    print("  Generating pytest script...\n")
    time.sleep(0.4)

    for line in PYTEST_OUTPUT.strip().split("\n"):
        _print_slow(f"    {line}", delay=0.008)

    print("\n  " + "-" * 50)
    print("  Demo complete!")
    print()
    print("  What just happened:")
    print("    1. ScreenForge inspected the page structure (inspect_ui)")
    print("    2. AI analyzed the DOM and chose actions")
    print("    3. Actions were executed step by step")
    print("    4. A production-ready pytest script was generated")
    print()
    print("  To do this for real:")
    print("    export OPENAI_API_KEY=sk-...")
    print("    screenforge --action click --platform web --locator-type text --locator-value 'Login'")
    print()
    print("  Star us on GitHub if this was useful!")
    print()

    return 0
