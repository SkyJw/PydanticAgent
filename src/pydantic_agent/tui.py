from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, LoadingIndicator, Markdown, Static

from pydantic_agent.agent import ProblemLocatorAgentRunner
from pydantic_agent.config import get_settings


class ProblemLocatorApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #workspace {
        height: 1fr;
        padding: 1 2;
    }

    #title {
        height: auto;
        margin-bottom: 1;
    }

    #output {
        height: 1fr;
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
    }

    #status-row {
        height: 1;
        margin-bottom: 1;
    }

    #busy {
        width: 4;
        display: none;
    }

    #status {
        width: 1fr;
    }

    #prompt-row {
        height: auto;
    }

    #prompt {
        width: 1fr;
        margin-right: 1;
    }

    Button {
        width: 12;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+r", "run_request", "Run"),
    ]

    def __init__(self, runner: ProblemLocatorAgentRunner | None = None) -> None:
        super().__init__()
        self.settings = get_settings()
        self.runner = runner or ProblemLocatorAgentRunner(self.settings)
        self.agent_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="workspace"):
            yield Static("底软问题辅助定位 Agent", id="title")
            yield Markdown(
                "输入故障现象、日志路径、网元 IP、账号、密码、SSH IP 后开始定位。",
                id="output",
            )
            with Horizontal(id="status-row"):
                yield LoadingIndicator(id="busy")
                yield Static("就绪", id="status")
            with Horizontal(id="prompt-row"):
                yield Input(placeholder="描述问题或直接闲聊...", id="prompt")
                yield Button("Run", id="run", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#prompt", Input).focus()

    @on(Button.Pressed, "#run")
    def run_button(self) -> None:
        self.action_run_request()

    @on(Input.Submitted, "#prompt")
    def prompt_submitted(self) -> None:
        self.action_run_request()

    def on_key(self, event: events.Key) -> None:
        if not isinstance(self.focused, Input):
            return

        keypad_map = {
            "0": "0",
            "1": "1",
            "2": "2",
            "3": "3",
            "4": "4",
            "5": "5",
            "6": "6",
            "7": "7",
            "8": "8",
            "9": "9",
            "decimal": ".",
            "add": "+",
            "subtract": "-",
            "multiply": "*",
            "divide": "/",
            "equal": "=",
            "separator": ",",
        }
        if event.key in {"enter", "keypad_enter", "kp_enter"}:
            event.stop()
            self.action_run_request()
            return
        if event.character is None and event.key in keypad_map:
            event.stop()
            self.focused.insert_text_at_cursor(keypad_map[event.key])

    def action_run_request(self) -> None:
        if self.agent_running:
            self.query_one("#status", Static).update("Agent 仍在运行，请稍候...")
            return

        prompt_input = self.query_one("#prompt", Input)
        prompt = prompt_input.value.strip()
        if not prompt:
            self.query_one("#output", Markdown).update("请输入问题描述或聊天内容。")
            return
        prompt_input.value = ""
        prompt_input.focus()
        self._run_agent(prompt)

    @work(exclusive=True)
    async def _run_agent(self, prompt: str) -> None:
        output = self.query_one("#output", Markdown)
        busy = self.query_one("#busy", LoadingIndicator)
        status = self.query_one("#status", Static)
        run_button = self.query_one("#run", Button)
        rendered = ""
        self.agent_running = True
        busy.display = True
        status.update("Agent 正在运行，大模型正在回答...")
        run_button.disabled = True
        output.update("运行中...")
        try:
            async for chunk in self.runner.stream_request(prompt):
                rendered += chunk
                output.update(rendered)
        except Exception as exc:
            output.update(f"运行失败：`{exc}`")
            status.update("运行失败")
        else:
            status.update("完成")
        finally:
            self.agent_running = False
            busy.display = False
            run_button.disabled = False
            self.query_one("#prompt", Input).focus()
