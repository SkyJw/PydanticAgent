import asyncio
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput, PromptedOutput, ToolOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelName
from pydantic_ai.providers.openai import OpenAIProvider

from pydantic_agent.config import Settings
from pydantic_agent.models import (
    AgentRunResult,
    IntentClassification,
    IntentType,
    RunStatus,
    TroubleshootingContext,
)

StructuredOutputModel = TypeVar("StructuredOutputModel", bound=BaseModel)
StructuredOutputMode = Literal["native", "tool", "prompted"]

INTENT_SYSTEM_PROMPT = """你是底层软件问题辅助定位 agent 的意图识别层。
只判断用户输入属于哪一种意图：
1. troubleshooting: 用户在描述故障、告警、日志、网元、SSH、定位、异常、复现、
   版本、业务中断等问题定位任务。
2. chat: 闲聊、问候、一般知识问题、非问题定位请求。
请给出结构化判断。"""

TROUBLESHOOTING_EXTRACT_PROMPT = """你是华为光传送底软问题定位场景的信息抽取器。
从用户输入中提取以下字段：
- log_path: 日志路径，可以是 Linux/Windows 路径、归档包路径或目录
- network_element_ip: 问题网元 IP
- username: 登录账号
- password: 登录密码
- ssh_ip: SSH 登录 IP、跳板机 IP 或设备管理 IP
- problem_description: 保留用户对现象、影响、时间、版本、操作步骤的描述
没有明确给出的字段填 null，不要编造。"""

CHAT_SYSTEM_PROMPT = "你是一个简洁友好的助手。对于闲聊直接回答，不要强行进入问题定位流程。"

TROUBLESHOOTING_SYSTEM_PROMPT = """你是华为光传送底软问题辅助定位 agent。
你擅长底层软件、网元、日志和 SSH 定位流程。当前阶段不要执行真实 SSH 操作，
不要假装已经读取日志。
请基于已抽取的信息输出：
1. 初步判断
2. 还缺哪些关键信息
3. 建议优先查看的日志/模块/时间窗口
4. 下一步定位命令或检查动作
如果账号密码已提供，只说明凭据已收到，不要在回答中回显密码。"""


class ProblemLocatorAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def handle_request(
        self,
        user_request: str,
        *,
        mock: bool | None = None,
    ) -> AgentRunResult:
        started_at = datetime.now()
        use_mock = self.settings.mock if mock is None else mock
        if use_mock:
            return self._mock_handle_request(user_request, started_at)

        classification = await self.classify_intent(user_request)
        if classification.intent is IntentType.CHAT:
            agent = self._build_agent(instructions=CHAT_SYSTEM_PROMPT)
            result = await self._run_agent(agent, user_request)
            return AgentRunResult(
                status=RunStatus.SUCCEEDED,
                output=str(result.output),
                model=self.settings.model_label,
                intent=classification.intent,
                intent_reason=classification.reason,
                started_at=started_at,
                finished_at=datetime.now(),
            )

        context = await self.extract_troubleshooting_context(user_request)
        agent = self._build_agent(instructions=TROUBLESHOOTING_SYSTEM_PROMPT)
        result = await self._run_agent(
            agent,
            self._build_troubleshooting_prompt(user_request, context),
        )
        output = f"{context.to_markdown()}\n\n### 定位建议\n\n{result.output}"
        return AgentRunResult(
            status=RunStatus.SUCCEEDED,
            output=output,
            model=self.settings.model_label,
            intent=classification.intent,
            intent_reason=classification.reason,
            troubleshooting_context=context,
            started_at=started_at,
            finished_at=datetime.now(),
        )

    async def stream_request(
        self,
        user_request: str,
        *,
        mock: bool | None = None,
    ) -> AsyncIterator[str]:
        use_mock = self.settings.mock if mock is None else mock
        if use_mock:
            result = self._mock_handle_request(user_request, datetime.now())
            for chunk in self._chunk_text(result.output):
                yield chunk
            return

        yield "### 意图识别\n\n"
        classification = await self.classify_intent(user_request)
        yield f"- 意图：`{classification.intent.value}`\n"
        yield f"- 置信度：`{classification.confidence:.2f}`\n"
        if classification.reason:
            yield f"- 理由：{classification.reason}\n"
        yield "\n"

        if classification.intent is IntentType.CHAT:
            agent = self._build_agent(instructions=CHAT_SYSTEM_PROMPT)
            async with asyncio.timeout(self.settings.request_timeout_seconds):
                async with agent.run_stream(
                    user_request,
                    retries=self.settings.model_retry_count,
                ) as response:
                    async for delta in response.stream_text(delta=True, debounce_by=None):
                        yield delta
            return

        context = await self.extract_troubleshooting_context(user_request)
        yield f"{context.to_markdown()}\n\n### 定位建议\n\n"
        agent = self._build_agent(instructions=TROUBLESHOOTING_SYSTEM_PROMPT)
        async with asyncio.timeout(self.settings.request_timeout_seconds):
            async with agent.run_stream(
                self._build_troubleshooting_prompt(user_request, context),
                retries=self.settings.model_retry_count,
            ) as response:
                async for delta in response.stream_text(delta=True, debounce_by=None):
                    yield delta

    async def classify_intent(self, user_request: str) -> IntentClassification:
        return await self._run_structured_output(
            IntentClassification,
            user_request,
            instructions=INTENT_SYSTEM_PROMPT,
        )

    async def extract_troubleshooting_context(self, user_request: str) -> TroubleshootingContext:
        return await self._run_structured_output(
            TroubleshootingContext,
            user_request,
            instructions=TROUBLESHOOTING_EXTRACT_PROMPT,
        )

    def build_model(self) -> str | OpenAIChatModel:
        if self.settings.model_provider == "pydantic-ai":
            return self.settings.model

        provider = OpenAIProvider(
            base_url=self.settings.openai_base_url,
            api_key=(
                self.settings.openai_api_key.get_secret_value()
                if self.settings.openai_api_key
                else None
            ),
        )
        return OpenAIChatModel(cast(OpenAIModelName, self.settings.model), provider=provider)

    def _build_agent(self, *, instructions: str, output_type: Any = str) -> Agent[Any, Any]:
        return Agent(
            self.build_model(),
            output_type=output_type,
            instructions=instructions,
            retries=self.settings.model_retry_count,
        )

    async def _run_agent(self, agent: Agent[Any, Any], user_request: str) -> Any:
        return await self._run_with_timeout(
            agent.run(
                user_request,
                retries=self.settings.model_retry_count,
            )
        )

    async def _run_with_timeout(self, awaitable: Any) -> Any:
        async with asyncio.timeout(self.settings.request_timeout_seconds):
            return await awaitable

    async def _run_structured_output(
        self,
        output_model: type[StructuredOutputModel],
        user_request: str,
        *,
        instructions: str,
    ) -> StructuredOutputModel:
        errors: list[str] = []
        for mode in self._structured_output_modes():
            try:
                return await self._run_structured_output_once(
                    output_model,
                    user_request,
                    instructions=instructions,
                    mode=mode,
                )
            except TimeoutError:
                errors.append(f"{mode}: timeout")
            except Exception as exc:
                errors.append(f"{mode}: {exc.__class__.__name__}")
                if self.settings.structured_output_mode != "auto":
                    raise

        raise RuntimeError(
            "结构化输出失败，已按配置尝试以下模式：" + "; ".join(errors)
        )

    async def _run_structured_output_once(
        self,
        output_model: type[StructuredOutputModel],
        user_request: str,
        *,
        instructions: str,
        mode: StructuredOutputMode,
    ) -> StructuredOutputModel:
        agent = self._build_agent(
            output_type=self._build_structured_output_type(output_model, mode),
            instructions=instructions,
        )
        result = await self._run_agent(agent, user_request)
        return cast(StructuredOutputModel, result.output)

    def _structured_output_modes(self) -> tuple[StructuredOutputMode, ...]:
        if self.settings.structured_output_mode == "auto":
            return ("native", "tool", "prompted")
        return (self.settings.structured_output_mode,)

    def _build_structured_output_type(
        self,
        output_model: type[StructuredOutputModel],
        mode: StructuredOutputMode,
    ) -> Any:
        if mode == "native":
            return NativeOutput(output_model)
        if mode == "tool":
            return ToolOutput(output_model, max_retries=self.settings.model_retry_count)
        return PromptedOutput(output_model)

    def _mock_handle_request(
        self,
        user_request: str,
        started_at: datetime,
    ) -> AgentRunResult:
        classification = self._mock_classify_intent(user_request)
        if classification.intent is IntentType.CHAT:
            return AgentRunResult(
                status=RunStatus.MOCKED,
                output=(
                    "[mock] 闲聊意图\n\n"
                    "你好，我是底软问题辅助定位 agent。你可以把故障现象、日志路径、"
                    "网元 IP、SSH 信息发给我。"
                ),
                model=self.settings.model_label,
                intent=classification.intent,
                intent_reason=classification.reason,
                started_at=started_at,
                finished_at=datetime.now(),
            )

        context = self._mock_extract_troubleshooting_context(user_request)
        output = "\n\n".join(
            [
                "[mock] 识别到问题定位意图",
                context.to_markdown(),
                "### 定位建议",
                "1. 先确认故障发生时间窗口，并按该时间过滤关键日志。",
                "2. 检查网元管理面连通性、进程状态和最近一次复位/升级记录。",
                "3. 后续可以接入 SSH 工具，自动拉取日志并执行只读检查命令。",
            ]
        )
        return AgentRunResult(
            status=RunStatus.MOCKED,
            output=output,
            model=self.settings.model_label,
            intent=classification.intent,
            intent_reason=classification.reason,
            troubleshooting_context=context,
            started_at=started_at,
            finished_at=datetime.now(),
        )

    def _mock_classify_intent(self, user_request: str) -> IntentClassification:
        keywords = [
            "问题",
            "故障",
            "定位",
            "日志",
            "网元",
            "告警",
            "异常",
            "ssh",
            "trace",
            "error",
            "core",
            "复位",
            "倒换",
            "中断",
        ]
        normalized = user_request.lower()
        matched = [keyword for keyword in keywords if keyword.lower() in normalized]
        if matched:
            return IntentClassification(
                intent=IntentType.TROUBLESHOOTING,
                confidence=0.85,
                reason=f"命中问题定位关键词：{', '.join(matched[:4])}",
            )
        return IntentClassification(
            intent=IntentType.CHAT,
            confidence=0.75,
            reason="未发现问题定位信息",
        )

    def _mock_extract_troubleshooting_context(self, user_request: str) -> TroubleshootingContext:
        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", user_request)
        ssh_ip = self._extract_after_label(user_request, ["ssh", "SSH"]) or (
            ips[-1] if ips else None
        )
        network_element_ip = self._extract_after_label(user_request, ["网元", "ne", "NE"]) or (
            ips[0] if ips else None
        )
        return TroubleshootingContext(
            log_path=self._extract_log_path(user_request),
            network_element_ip=network_element_ip,
            username=self._extract_after_label(user_request, ["账号", "用户", "user", "username"]),
            password=self._extract_after_label(user_request, ["密码", "pass", "password"]),
            ssh_ip=ssh_ip,
            problem_description=user_request.strip(),
        )

    def _build_troubleshooting_prompt(
        self,
        user_request: str,
        context: TroubleshootingContext,
    ) -> str:
        safe_context = context.model_copy(
            update={"problem_description": context.redacted_problem_description()}
        )
        return "\n".join(
            [
                "用户原始输入：",
                context.redacted_problem_description() or user_request.strip(),
                "",
                "已抽取结构化信息：",
                safe_context.model_dump_json(exclude={"password"}, indent=2),
                "password_present: " + str(bool(context.password)),
                "",
                "请输出底软问题定位建议，不要回显密码。",
            ]
        )

    def _extract_log_path(self, text: str) -> str | None:
        patterns = [
            r"(?:日志路径|log_path|log path|logs?|路径)[:：=]\s*([^\s,，;；]+)",
            r"((?:/[A-Za-z0-9._-]+)+/?(?:[A-Za-z0-9._-]+\.(?:log|zip|tar|gz|tgz))?)",
            r"([A-Za-z]:\\[^\s,，;；]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_after_label(self, text: str, labels: list[str]) -> str | None:
        for label in labels:
            pattern = rf"{re.escape(label)}\s*(?:是|为|:|：|=)?\s*([^\s,，;；]+)"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _chunk_text(self, text: str, size: int = 24) -> list[str]:
        return [text[index : index + size] for index in range(0, len(text), size)]
