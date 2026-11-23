import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from memimpact.providers.base import ToolCall, ToolCallCompletion

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
REASONING_EFFORT_ENV = "MEMIMPACT_REASONING_EFFORT"


def reasoning_effort_value(thinking: bool) -> str | None:
    """Map the project thinking flag onto Ollama's reasoning_effort field.

    Thinking off always requests ``none``. Thinking on uses
    ``MEMIMPACT_REASONING_EFFORT`` when set, and otherwise leaves the field
    unset so the model default applies.
    """
    if not thinking:
        return "none"
    load_dotenv()
    effort = os.environ.get(REASONING_EFFORT_ENV, "").strip()
    return effort or None


def make_ollama_client() -> OpenAI:
    load_dotenv()
    base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
    api_key = os.environ.get("OLLAMA_API_KEY", "ollama")
    return OpenAI(api_key=api_key, base_url=base_url)


class OllamaProvider:
    name = "ollama"

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client or make_ollama_client()

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        *,
        thinking: bool,
    ) -> ToolCallCompletion:
        # /v1 has no enable_thinking. reasoning_effort "none" maps to think=false.
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
        }
        effort = reasoning_effort_value(thinking)
        if effort is not None:
            request["extra_body"] = {"reasoning_effort": effort}
        response = self._client.chat.completions.create(**request)
        message = response.choices[0].message
        tool_calls = [
            ToolCall(
                name=tool_call.function.name,
                arguments_json=tool_call.function.arguments,
            )
            for tool_call in (message.tool_calls or [])
        ]
        usage = response.usage.model_dump() if response.usage else None
        return ToolCallCompletion(
            content=message.content,
            tool_calls=tool_calls,
            usage=usage,
        )

    def as_openai_client(self) -> OpenAI:
        return self._client
