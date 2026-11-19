import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from memimpact.providers.base import ToolCall, ToolCallCompletion

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"


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
        del thinking  # Recorded by callers; Ollama has no DashScope thinking flag.
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
        )
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
