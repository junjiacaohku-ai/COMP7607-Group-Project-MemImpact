import json
import time
from typing import Any

from tool_sandbox.common.tool_conversion import convert_to_openai_tools
from tool_sandbox.tools.contact import search_contacts
from tool_sandbox.tools.messaging import send_message_with_phone_number
from tool_sandbox.tools.reminder import add_reminder, remove_reminder, search_reminder

from memimpact.core import CandidateAction, MemoryRecord
from memimpact.prompts import PLANNER_PROMPT_SHA256, PLANNER_SYSTEM_PROMPT
from memimpact.qwen import make_qwen_client

TOOL_REGISTRY = {
    "search_contacts": search_contacts,
    "send_message_with_phone_number": send_message_with_phone_number,
    "add_reminder": add_reminder,
    "search_reminder": search_reminder,
    "remove_reminder": remove_reminder,
}


class PlannerError(ValueError):
    def __init__(self, message: str, trace: dict[str, Any]) -> None:
        super().__init__(message)
        self.trace = trace


class CandidatePlanner:
    def __init__(
        self,
        model: str,
        temperature: float,
        thinking: bool = True,
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.model = model
        self.temperature = temperature
        self.thinking = thinking
        self.max_attempts = max_attempts
        self.client = make_qwen_client()

    def plan(
        self,
        user_prompt: str,
        memories: list[MemoryRecord],
        tool_names: list[str],
        verified_evidence: list[dict[str, Any]] | None = None,
    ) -> tuple[CandidateAction, dict[str, Any]]:
        evidence = verified_evidence or []
        tools = convert_to_openai_tools(
            {name: TOOL_REGISTRY[name] for name in tool_names}
        )
        memory_payload = [memory.model_dump() for memory in memories]
        messages = [
            {
                "role": "system",
                "content": PLANNER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": user_prompt,
                        "retrieved_memories": memory_payload,
                        "verified_evidence": evidence,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": self.temperature,
            "extra_body": {"parallel_tool_calls": False},
        }
        if not self.thinking:
            request["extra_body"]["enable_thinking"] = False

        attempts = []
        final_action = None
        for attempt_index in range(self.max_attempts):
            started = time.perf_counter()
            response = self.client.chat.completions.create(**request)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            attempt = {
                "attempt_index": attempt_index,
                "latency_ms": latency_ms,
                "usage": response.usage.model_dump() if response.usage else None,
                "tool_call_count": len(tool_calls),
                "content": message.content,
                "error": None,
            }
            attempts.append(attempt)
            if len(tool_calls) != 1:
                attempt["error"] = "Expected exactly one tool call"
                continue
            try:
                action = CandidateAction(
                    tool_name=tool_calls[0].function.name,
                    arguments=json.loads(tool_calls[0].function.arguments),
                )
            except (ValueError, TypeError) as error:
                attempt["error"] = str(error)
                continue
            final_action = action
            attempt["action"] = action.model_dump()
            break

        trace = {
            "model": self.model,
            "temperature": self.temperature,
            "thinking": self.thinking,
            "planner_prompt_sha256": PLANNER_PROMPT_SHA256,
            "visible_memory_ids": [memory.memory_id for memory in memories],
            "visible_memories": memory_payload,
            "verified_evidence": evidence,
            "action": final_action.model_dump() if final_action else None,
            "canonical_action": final_action.canonical() if final_action else None,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "latency_ms": round(sum(attempt["latency_ms"] for attempt in attempts), 3),
            "usage": {
                key: sum(
                    attempt["usage"][key] for attempt in attempts if attempt["usage"]
                )
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
        }
        if final_action is None:
            raise PlannerError(
                f"Planner failed to produce one valid tool call after {len(attempts)} attempts",
                trace,
            )
        return final_action, trace
