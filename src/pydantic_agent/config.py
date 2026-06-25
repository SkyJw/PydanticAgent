from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and .env."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PYDANTIC_AGENT_")

    model_provider: Literal["openai-compatible", "pydantic-ai"] = Field(
        default="openai-compatible",
        description="Model loading mode. Use pydantic-ai to pass model through unchanged.",
    )
    structured_output_mode: Literal["auto", "native", "tool", "prompted"] = Field(
        default="auto",
        description="Structured output mode. auto tries native, then tool, then prompted output.",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Timeout in seconds for each LLM request attempt.",
    )
    model: str = Field(default="gpt-5.2", description="Model name or Pydantic AI model string")
    openai_base_url: str | None = Field(
        default=None,
        description="OpenAI-compatible API base URL, for example https://api.openai.com/v1",
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="API key for OpenAI-compatible providers",
    )
    mock: bool = Field(default=False, description="Return deterministic responses without an LLM")

    @field_validator("openai_base_url", "openai_api_key", mode="before")
    @classmethod
    def _blank_string_as_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def model_label(self) -> str:
        if self.model_provider == "pydantic-ai":
            return self.model
        if self.openai_base_url:
            return f"openai-compatible:{self.model}@{self.openai_base_url}"
        return f"openai-compatible:{self.model}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
