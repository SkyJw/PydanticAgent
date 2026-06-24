import asyncio
from typing import Annotated, Literal, cast

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.panel import Panel

from pydantic_agent.agent import ProblemLocatorAgentRunner
from pydantic_agent.config import get_settings

app = typer.Typer(help="底软问题辅助定位 agent")
console = Console()


@app.command()
def run(
    prompt: Annotated[str, typer.Argument(help="User request to process")],
    mock: Annotated[bool, typer.Option("--mock", help="Run without calling an LLM")] = False,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="openai-compatible or pydantic-ai"),
    ] = None,
    model: Annotated[str | None, typer.Option("--model", help="Override model name")] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Override OpenAI-compatible base URL"),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="Override OpenAI-compatible API key"),
    ] = None,
) -> None:
    """Run the problem locator agent from the command line."""

    settings = get_settings()
    if provider is not None:
        if provider not in {"openai-compatible", "pydantic-ai"}:
            raise typer.BadParameter("provider must be openai-compatible or pydantic-ai")
        settings.model_provider = cast(Literal["openai-compatible", "pydantic-ai"], provider)
    if model is not None:
        settings.model = model
    if base_url is not None:
        settings.openai_base_url = base_url
    if api_key is not None:
        settings.openai_api_key = SecretStr(api_key)

    runner = ProblemLocatorAgentRunner(settings)
    result = asyncio.run(runner.handle_request(prompt, mock=mock))
    title_parts = ["底软问题辅助定位", result.status.value]
    if result.intent:
        title_parts.append(result.intent.value)
    console.print(
        Panel(
            result.output,
            title=" · ".join(title_parts),
            subtitle=f"model={result.model}",
            border_style="cyan",
        )
    )


@app.command()
def tui() -> None:
    """Open the Textual interface."""

    from pydantic_agent.tui import ProblemLocatorApp

    ProblemLocatorApp().run()
