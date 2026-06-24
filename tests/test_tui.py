import pytest
from textual.widgets import Input, Static

from pydantic_agent.agent import ProblemLocatorAgentRunner
from pydantic_agent.config import Settings
from pydantic_agent.tui import ProblemLocatorApp

pytestmark = pytest.mark.anyio


async def test_tui_clears_input_after_submit() -> None:
    runner = ProblemLocatorAgentRunner(Settings(mock=True))
    app = ProblemLocatorApp(runner=runner)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", Input)
        prompt.value = "日志路径 /tmp/a.log 网元 1.1.1.1 故障定位"

        app.action_run_request()
        assert prompt.value == ""

        await pilot.pause()
        await pilot.pause()

        assert app.query_one("#status", Static).content == "完成"


async def test_tui_maps_keypad_decimal_to_dot() -> None:
    runner = ProblemLocatorAgentRunner(Settings(mock=True))
    app = ProblemLocatorApp(runner=runner)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", Input)
        prompt.focus()

        await pilot.press("decimal")

        assert prompt.value == "."
