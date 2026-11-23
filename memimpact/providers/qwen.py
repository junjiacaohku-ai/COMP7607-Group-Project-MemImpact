import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from memimpact.providers.base import ToolCall, ToolCallCompletion


def make_dashscope_client() -> OpenAI:
    load_dotenv()
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not set")

    base_url = os.environ.get("DASHSCOPE_BASE_URL")
    if not base_url:
        workspace_id = os.environ.get("DASHSCOPE_WORKSPACE_ID")
        if not workspace_id:
            raise RuntimeError(
                "Set DASHSCOPE_WORKSPACE_ID or provide the full DASHSCOPE_BASE_URL"
            )
        region = os.environ.get("DASHSCOPE_REGION", "cn-beijing")
        base_url = (
            f"https://{workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1"
        )

    return OpenAI(api_key=api_key, base_url=base_url)


class QwenProvider:
    name = "qwen"

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client or make_dashscope_client()

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        *,
        thinking: bool,
    ) -> ToolCallCompletion:
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "extra_body": {"parallel_tool_calls": False},
        }
        if not thinking:
            request["extra_body"]["enable_thinking"] = False

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
