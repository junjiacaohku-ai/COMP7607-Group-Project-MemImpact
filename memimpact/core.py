import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class MemoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str
    claim: str
    entity: str
    scope: str
    timestamp: str
    provenance: str


class VerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str
    status: Literal["confirmed", "refuted", "unknown"]
    evidence: dict[str, Any] | None


class CandidateAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    arguments: dict[str, Any]

    def canonical(self) -> str:
        return json.dumps(
            {
                "tool_name": self.tool_name,
                "arguments": self.arguments,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )


def remove_memory(
    memories: list[MemoryRecord], memory_id: str
) -> list[MemoryRecord]:
    remaining = [memory for memory in memories if memory.memory_id != memory_id]
    if len(remaining) != len(memories) - 1:
        raise ValueError(f"Expected to remove exactly one memory: {memory_id}")
    return remaining


def actions_equal(left: CandidateAction, right: CandidateAction) -> bool:
    return left.canonical() == right.canonical()


def action_flip_rate(
    full_actions: list[CandidateAction], ablated_actions: list[CandidateAction]
) -> float:
    if not full_actions or len(full_actions) != len(ablated_actions):
        raise ValueError("Paired action lists must be non-empty and have equal length")
    flips = sum(
        not actions_equal(full, ablated)
        for full, ablated in zip(full_actions, ablated_actions, strict=True)
    )
    return flips / len(full_actions)


def baseline_flip_rate(full_actions: list[CandidateAction]) -> float:
    if len(full_actions) < 2:
        return 0.0
    comparisons = [
        (left, right)
        for index, left in enumerate(full_actions)
        for right in full_actions[index + 1 :]
    ]
    return sum(not actions_equal(left, right) for left, right in comparisons) / len(
        comparisons
    )


def noise_adjusted_impact(action_flip: float, baseline_flip: float) -> float:
    return max(0.0, action_flip - baseline_flip)
