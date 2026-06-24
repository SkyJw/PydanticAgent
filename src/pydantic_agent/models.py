from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MOCKED = "mocked"


class IntentType(StrEnum):
    CHAT = "chat"
    TROUBLESHOOTING = "troubleshooting"


class IntentClassification(BaseModel):
    intent: IntentType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class TroubleshootingContext(BaseModel):
    log_path: str | None = Field(default=None, description="Path to the relevant logs")
    network_element_ip: str | None = Field(default=None, description="Problem network element IP")
    username: str | None = Field(default=None, description="Login account")
    password: str | None = Field(default=None, repr=False, description="Login password")
    ssh_ip: str | None = Field(default=None, description="SSH jump host or device IP")
    problem_description: str = Field(default="", description="User's problem description")

    def missing_fields(self) -> list[str]:
        field_names = {
            "log_path": "日志路径",
            "network_element_ip": "问题网元IP",
            "username": "账号",
            "password": "密码",
            "ssh_ip": "SSH IP",
            "problem_description": "问题描述",
        }
        return [label for name, label in field_names.items() if not getattr(self, name)]

    def redacted_problem_description(self) -> str:
        if not self.password:
            return self.problem_description
        return self.problem_description.replace(self.password, "***")

    def to_markdown(self) -> str:
        password = "***" if self.password else "未提供"
        rows = [
            ("日志路径", self.log_path or "未提供"),
            ("问题网元IP", self.network_element_ip or "未提供"),
            ("账号", self.username or "未提供"),
            ("密码", password),
            ("SSH IP", self.ssh_ip or "未提供"),
            ("问题描述", self.redacted_problem_description() or "未提供"),
        ]
        lines = ["### 已抽取的问题定位信息", ""]
        lines.extend(f"- **{label}**: {value}" for label, value in rows)
        missing = self.missing_fields()
        if missing:
            lines.extend(["", f"> 缺失字段：{', '.join(missing)}"])
        return "\n".join(lines)


class AgentRunResult(BaseModel):
    status: RunStatus
    output: str
    model: str | None = None
    intent: IntentType | None = None
    intent_reason: str | None = None
    troubleshooting_context: TroubleshootingContext | None = None
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime = Field(default_factory=datetime.now)
