from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from openai import OpenAI


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments_json: str


@dataclass(frozen=True)
class ToolCallCompletion:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] | None = None


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        *,
        thinking: bool,
    ) -> ToolCallCompletion:
        """Run one chat completion that may return tool calls."""

    def as_openai_client(self) -> OpenAI:
        """Return an OpenAI-compatible client for ToolSandbox roles."""
