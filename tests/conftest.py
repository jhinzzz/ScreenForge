"""Shared fixtures for framework unit tests."""

from unittest.mock import MagicMock, PropertyMock

import pytest


@pytest.fixture
def mock_page():
    """Mock Playwright Page object with common methods."""
    page = MagicMock()
    page.evaluate = MagicMock(return_value='{"ui_elements": []}')
    page.screenshot = MagicMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # Locator chain
    locator = MagicMock()
    locator.first = locator
    locator.click = MagicMock()
    locator.fill = MagicMock()
    locator.hover = MagicMock()
    locator.wait_for = MagicMock()
    locator.is_visible = MagicMock(return_value=True)
    locator.inner_text = MagicMock(return_value="hello")
    page.locator = MagicMock(return_value=locator)
    page.get_by_text = MagicMock(return_value=locator)

    # Mouse
    page.mouse = MagicMock()
    page.mouse.click = MagicMock()
    page.mouse.wheel = MagicMock()

    # Keyboard
    page.keyboard = MagicMock()
    page.keyboard.press = MagicMock()

    # Navigation
    page.goto = MagicMock()
    page.wait_for_timeout = MagicMock()

    return page


@pytest.fixture
def mock_openai_client(monkeypatch):
    """Patch OpenAI client to return configurable responses."""
    client = MagicMock()

    def make_response(content: str):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = content
        return response

    client.chat.completions.create = MagicMock(
        return_value=make_response('{"x": 100, "y": 200}')
    )
    client._make_response = make_response

    return client


@pytest.fixture
def sample_ui_elements():
    """Known element list with ref/coordinates."""
    return [
        {
            "ref": "@1",
            "class": "button",
            "clickable": True,
            "id": "submit-btn",
            "text": "Submit",
            "x": 100,
            "y": 200,
            "w": 80,
            "h": 30,
        },
        {
            "ref": "@2",
            "class": "a",
            "clickable": True,
            "text": "Home",
            "x": 10,
            "y": 10,
            "w": 60,
            "h": 20,
        },
        {
            "ref": "@3",
            "class": "span",
            "clickable": False,
            "text": "Label text",
            "x": 200,
            "y": 300,
            "w": 100,
            "h": 16,
        },
        {
            "ref": "@4",
            "class": "div",
            "clickable": True,
            "text": "Tiny",
            "x": 50,
            "y": 50,
            "w": 0,
            "h": 0,
        },
    ]
