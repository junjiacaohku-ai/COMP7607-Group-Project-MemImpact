import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from memimpact.providers.base import ToolCall, ToolCallCompletion
from memimpact.providers.reasoning import reasoning_effort_value


def make_openai_client() -> OpenAI:
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


class OpenAIProvider:
    name = "openai"

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client or make_openai_client()

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        *,
        thinking: bool,
    ) -> ToolCallCompletion:
        extra_body: dict[str, Any] = {"parallel_tool_calls": False}
        effort = reasoning_effort_value(thinking)
        if effort is not None:
            extra_body["reasoning_effort"] = effort
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            extra_body=extra_body,
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
