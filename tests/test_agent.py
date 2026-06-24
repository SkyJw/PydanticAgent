import asyncio

from pydantic_agent.agent import ProblemLocatorAgentRunner
from pydantic_agent.config import Settings
from pydantic_agent.models import IntentType


def test_settings_can_enable_mock_mode() -> None:
    settings = Settings(mock=True)

    assert settings.mock is True


def test_runner_builds_openai_compatible_model() -> None:
    runner = ProblemLocatorAgentRunner(
        Settings(
            model="deepseek-chat",
            openai_base_url="https://api.deepseek.com/v1",
            openai_api_key="test-key",
        )
    )

    model = runner.build_model()

    assert model.model_name == "deepseek-chat"
    assert model.base_url == "https://api.deepseek.com/v1/"


def test_runner_can_still_use_pydantic_ai_model_string() -> None:
    runner = ProblemLocatorAgentRunner(
        Settings(model_provider="pydantic-ai", model="openai:gpt-5.2")
    )

    assert runner.build_model() == "openai:gpt-5.2"


def test_mock_route_recognizes_chat_intent() -> None:
    runner = ProblemLocatorAgentRunner(Settings(mock=True))

    result = asyncio.run(runner.handle_request("你好，今天状态如何"))

    assert result.intent is IntentType.CHAT
    assert result.troubleshooting_context is None


def test_mock_route_extracts_troubleshooting_context() -> None:
    runner = ProblemLocatorAgentRunner(Settings(mock=True))
    prompt = (
        "请定位问题，网元 192.168.1.10 业务中断，日志路径 /var/log/otn/fault.log，"
        "账号 admin 密码 Huawei123 ssh 10.10.10.8"
    )

    result = asyncio.run(runner.handle_request(prompt))

    assert result.intent is IntentType.TROUBLESHOOTING
    assert result.troubleshooting_context is not None
    assert result.troubleshooting_context.log_path == "/var/log/otn/fault.log"
    assert result.troubleshooting_context.network_element_ip == "192.168.1.10"
    assert result.troubleshooting_context.username == "admin"
    assert result.troubleshooting_context.password == "Huawei123"
    assert result.troubleshooting_context.ssh_ip == "10.10.10.8"
    assert "Huawei123" not in result.output


def test_mock_stream_request_yields_incremental_output() -> None:
    async def collect() -> list[str]:
        runner = ProblemLocatorAgentRunner(Settings(mock=True))
        return [
            chunk
            async for chunk in runner.stream_request(
                "日志路径 /tmp/a.log 网元 1.1.1.1 故障定位"
            )
        ]

    chunks = asyncio.run(collect())

    assert len(chunks) > 1
    assert "问题定位" in "".join(chunks)
