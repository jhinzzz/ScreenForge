"""Tests for cli/shorthand.py — shorthand command expansion."""

from cli.shorthand import _detect_locator_type, preprocess_argv


class TestDetectLocatorType:
    def test_ref_prefix(self):
        assert _detect_locator_type("@3") == "ref"

    def test_css_hash(self):
        assert _detect_locator_type("#email") == "css"

    def test_css_dot(self):
        assert _detect_locator_type(".btn-primary") == "css"

    def test_css_bracket(self):
        assert _detect_locator_type("[data-testid=login]") == "css"

    def test_plain_text(self):
        assert _detect_locator_type("Login") == "text"

    def test_empty_string(self):
        assert _detect_locator_type("") == "text"


class TestPreprocessArgv:
    def test_passthrough_flag_mode(self):
        argv = ["screenforge", "--action", "click", "--locator-type", "text", "--locator-value", "Login"]
        assert preprocess_argv(argv) == argv

    def test_click_text(self):
        result = preprocess_argv(["screenforge", "click", "Login"])
        assert "--action" in result
        assert "click" in result
        assert "--locator-type" in result
        assert "text" in result
        assert "--locator-value" in result
        assert "Login" in result

    def test_click_css(self):
        result = preprocess_argv(["screenforge", "click", "#email"])
        idx = result.index("--locator-type")
        assert result[idx + 1] == "css"

    def test_click_ref(self):
        result = preprocess_argv(["screenforge", "click", "@3"])
        idx = result.index("--locator-type")
        assert result[idx + 1] == "ref"

    def test_input_with_value(self):
        result = preprocess_argv(["screenforge", "input", "#email", "admin@test.com"])
        assert "--extra-value" in result
        assert "admin@test.com" in result
        idx = result.index("--locator-value")
        assert result[idx + 1] == "#email"

    def test_goto_url(self):
        result = preprocess_argv(["screenforge", "goto", "https://example.com"])
        assert "--action" in result
        assert "goto" in result
        assert "--extra-value" in result
        assert "https://example.com" in result
        assert "--locator-type" not in result

    def test_press_key(self):
        result = preprocess_argv(["screenforge", "press", "Enter"])
        assert "--action" in result
        assert "press" in result
        assert "--extra-value" in result
        assert "Enter" in result

    def test_swipe_direction(self):
        result = preprocess_argv(["screenforge", "swipe", "up"])
        assert "--action" in result
        assert "swipe" in result
        assert "--extra-value" in result
        assert "up" in result

    def test_inspect_shorthand(self):
        result = preprocess_argv(["screenforge", "inspect"])
        assert "--tool-stdin" in result

    def test_demo_shorthand(self):
        result = preprocess_argv(["screenforge", "demo"])
        assert "--demo" in result

    def test_unknown_command_passthrough(self):
        argv = ["screenforge", "unknown_command", "arg1"]
        assert preprocess_argv(argv) == argv

    def test_no_args_passthrough(self):
        argv = ["screenforge"]
        assert preprocess_argv(argv) == argv

    def test_platform_flag_preserved(self):
        result = preprocess_argv(["screenforge", "click", "Login", "--platform", "android"])
        assert "--platform" in result
        idx = result.index("--platform")
        assert result[idx + 1] == "android"

    def test_default_platform_web(self):
        result = preprocess_argv(["screenforge", "click", "Login"])
        idx = result.index("--platform")
        assert result[idx + 1] == "web"

    def test_assert_text_equals_expansion(self):
        result = preprocess_argv(["screenforge", "assert_text_equals", "#title", "Welcome"])
        assert "--action" in result
        assert "assert_text_equals" in result
        assert "--locator-type" in result
        assert "--locator-value" in result
        idx_lv = result.index("--locator-value")
        assert result[idx_lv + 1] == "#title"
        assert "--extra-value" in result
        idx_ev = result.index("--extra-value")
        assert result[idx_ev + 1] == "Welcome"

    def test_passthrough_tool_stdin_flag(self):
        argv = ["screenforge", "--tool-stdin"]
        assert preprocess_argv(argv) == argv

    def test_passthrough_already_expanded(self):
        argv = ["screenforge", "--action", "click", "--platform", "ios"]
        assert preprocess_argv(argv) == argv
