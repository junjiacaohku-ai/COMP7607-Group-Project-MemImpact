import copy
import json
from pathlib import Path
from typing import Any

from memimpact.core import (
    MemoryRecord,
    action_flip_rate,
    baseline_flip_rate,
    noise_adjusted_impact,
    remove_memory,
)
from memimpact.planner import CandidatePlanner, PlannerError
from memimpact.scoring import observable_uncertainty, verification_score
from memimpact.toolsandbox_adapter import execute_fixture_action
from memimpact.verification import AuthoritativeContactVerifier

POLICIES = (
    "memimpact",
    "memimpact_flip",
    "always_proceed",
    "always_verify",
    "static",
    "amv_guard",
)
MEMIMPACT_POLICIES = ("memimpact", "memimpact_flip")


def candidate_conditioned_memories(
    memories: list[MemoryRecord], action: Any
) -> list[MemoryRecord]:
    argument_values = []
    for value in action.arguments.values():
        text = str(value).strip()
        if len(text) >= 3:
            argument_values.append(text)
        if isinstance(value, float) and value.is_integer():
            argument_values.append(str(int(value)))
    return [
        memory
        for memory in memories
        if any(value in memory.claim for value in argument_values)
    ]


def run_episode(
    fixture: dict[str, Any],
    policy: str,
    planner: CandidatePlanner,
    samples: int,
    output_directory: Path,
    verification_budget: int = 1,
    cached_full_runs: list[tuple[Any, dict[str, Any]]] | None = None,
    cached_ablated_runs: dict[str, list[tuple[Any, dict[str, Any]]]] | None = None,
    forced_memory_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")
    if samples < 1 or verification_budget < 0:
        raise ValueError("samples and verification_budget must be non-negative")

    memories = [MemoryRecord(**memory) for memory in fixture["memories"]]
    traces = []

    def call_planner(
        condition: str,
        sample_index: int | None,
        visible_memories: list[MemoryRecord],
        removed_memory_id: str | None = None,
        verified_evidence: list[dict] | None = None,
    ):
        try:
            action, trace = planner.plan(
                fixture["user_prompt"],
                visible_memories,
                fixture["available_tools"],
                verified_evidence=verified_evidence,
            )
        except PlannerError as error:
            error.trace.update(
                {
                    "condition": condition,
                    "removed_memory_id": removed_memory_id,
                    "sample_index": sample_index,
                }
            )
            traces.append(error.trace)
            output_directory.mkdir(parents=True, exist_ok=True)
            (output_directory / "trace.json").write_text(
                json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (output_directory / "error_summary.json").write_text(
                json.dumps(
                    {
                        "scenario_id": fixture["scenario_id"],
                        "policy": policy,
                        "error": str(error),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            raise
        trace.update(
            {
                "condition": condition,
                "removed_memory_id": removed_memory_id,
                "sample_index": sample_index,
            }
        )
        traces.append(trace)
        return action

    full_samples = samples if policy in MEMIMPACT_POLICIES else 1
    if cached_full_runs is None:
        full_runs = [
            (call_planner("full", sample_index, memories), traces[-1])
            for sample_index in range(full_samples)
        ]
    else:
        if len(cached_full_runs) < full_samples:
            raise ValueError("Not enough cached full-memory runs")
        full_runs = []
        for action, trace in cached_full_runs[:full_samples]:
            cached_trace = copy.deepcopy(trace)
            cached_trace["shared_across_policies"] = True
            traces.append(cached_trace)
            full_runs.append((action, cached_trace))
    full_actions = [action for action, _ in full_runs]
    initial_action = full_actions[0]
    baseline_flip = (
        baseline_flip_rate(full_actions) if policy in MEMIMPACT_POLICIES else None
    )
    comparisons = []

    if policy in MEMIMPACT_POLICIES:
        for memory in memories:
            if cached_ablated_runs is None:
                remaining = remove_memory(memories, memory.memory_id)
                ablated_runs = [
                    (
                        call_planner(
                            "single_memory_removed",
                            sample_index,
                            remaining,
                            memory.memory_id,
                        ),
                        traces[-1],
                    )
                    for sample_index in range(samples)
                ]
            else:
                cached_runs = cached_ablated_runs[memory.memory_id]
                if len(cached_runs) < samples:
                    raise ValueError("Not enough cached ablated runs")
                ablated_runs = []
                for action, trace in cached_runs[:samples]:
                    cached_trace = copy.deepcopy(trace)
                    cached_trace["shared_across_policies"] = True
                    traces.append(cached_trace)
                    ablated_runs.append((action, cached_trace))
            ablated_actions = [action for action, _ in ablated_runs]
            raw_flip = action_flip_rate(full_actions, ablated_actions)
            impact = noise_adjusted_impact(raw_flip, baseline_flip)
            uncertainty = observable_uncertainty(
                memory, fixture.get("current_time", "2026-01-01T00:00:00+08:00")
            )
            selection_score = (
                impact
                if policy == "memimpact_flip"
                else verification_score(
                    memory,
                    impact,
                    fixture.get("current_time", "2026-01-01T00:00:00+08:00"),
                    consequence=fixture.get("action_consequence", 1.0),
                )
            )
            comparisons.append(
                {
                    "removed_memory_id": memory.memory_id,
                    "ablated_actions": [
                        action.model_dump() for action in ablated_actions
                    ],
                    "raw_action_flip_rate": raw_flip,
                    "baseline_flip_rate": baseline_flip,
                    "noise_adjusted_impact": impact,
                    "observable_uncertainty": uncertainty,
                    "selection_score": selection_score,
                }
            )

    flipped_memory_ids = [
        item["removed_memory_id"]
        for item in comparisons
        if item["raw_action_flip_rate"] > 0
    ]
    ranked_memory_ids = [
        item["removed_memory_id"]
        for item in sorted(
            comparisons,
            key=lambda item: item["selection_score"],
            reverse=True,
        )
        if item["selection_score"] > 0
    ]

    task_family = fixture.get("task_family", "messaging")
    critical_scopes = (
        {"contact"}
        if task_family == "messaging"
        else {"reminder", "reminder_time", "reminder_target"}
    )
    if forced_memory_id is not None:
        selected_memories = [
            memory for memory in memories if memory.memory_id == forced_memory_id
        ]
        if len(selected_memories) != 1:
            raise ValueError(f"Unknown forced memory: {forced_memory_id}")
    elif policy == "always_proceed":
        selected_memories = []
    elif policy == "always_verify":
        selected_memories = memories
    elif policy == "static":
        selected_memories = sorted(
            (memory for memory in memories if memory.scope in critical_scopes),
            key=lambda memory: memory.timestamp,
        )[:verification_budget]
    elif policy == "amv_guard":
        selected_memories = candidate_conditioned_memories(
            memories, initial_action
        )[:verification_budget]
    else:
        selected_by_id = {memory.memory_id: memory for memory in memories}
        selected_memories = [
            selected_by_id[memory_id]
            for memory_id in ranked_memory_ids[:verification_budget]
        ]

    verifier = AuthoritativeContactVerifier(
        fixture.get("authoritative_contacts", []),
        fixture.get("verification_overrides"),
    )
    verification_results = []
    verified_evidence = []
    unresolved_critical = False
    for memory in selected_memories:
        verification = verifier.verify(memory)
        verification_results.append(verification.model_dump())
        if verification.status == "refuted":
            verified_evidence.append(verification.evidence)
        elif verification.status == "unknown" and memory.scope in critical_scopes:
            unresolved_critical = True

    if task_family == "messaging":
        target_tool = "send_message_with_phone_number"
    elif task_family == "reminder_creation":
        target_tool = "add_reminder"
    else:
        target_tool = "remove_reminder"
    lookup_tools = (
        {"search_contacts"} if task_family == "messaging" else {"search_reminder"}
    )
    final_action = initial_action
    decision = "proceed"
    if verified_evidence:
        final_action = call_planner(
            "replan_after_refutation",
            None,
            memories,
            verified_evidence=verified_evidence,
        )
        verified_values = {
            key: {
                evidence[key] for evidence in verified_evidence if key in evidence
            }
            for key in ("phone_number", "reminder_timestamp", "reminder_id")
        }
        if final_action.tool_name not in {target_tool, *lookup_tools}:
            decision = "abstain"
        elif final_action.tool_name == target_tool:
            for key, values in verified_values.items():
                if values and final_action.arguments.get(key) not in values:
                    decision = "abstain"
    elif unresolved_critical:
        decision = "abstain"

    lookup_execution = None
    if decision == "proceed" and final_action.tool_name in lookup_tools:
        lookup_execution = execute_fixture_action(final_action, fixture)
        lookup_records = lookup_execution["tool_result"]
        if not lookup_records:
            decision = "abstain"
        else:
            lookup_evidence = {
                "type": "authoritative_tool_result",
                "tool_name": final_action.tool_name,
                "records": lookup_records,
            }
            final_action = call_planner(
                "replan_after_lookup",
                None,
                memories,
                verified_evidence=[*verified_evidence, lookup_evidence],
            )
            if task_family == "messaging":
                lookup_field = "phone_number"
            elif task_family == "reminder_creation":
                lookup_field = "reminder_timestamp"
            else:
                lookup_field = "reminder_id"
            lookup_values = {
                record[lookup_field]
                for record in lookup_records
                if lookup_field in record
            }
            if final_action.tool_name != target_tool or (
                lookup_values
                and final_action.arguments.get(lookup_field) not in lookup_values
            ):
                decision = "abstain"

    execution = None
    if decision == "proceed":
        execution = execute_fixture_action(final_action, fixture)
        if lookup_execution is not None:
            execution["lookup"] = lookup_execution

    total_usage = {
        key: sum(trace["usage"][key] for trace in traces)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    result = {
        "scenario_id": fixture["scenario_id"],
        "base_scenario_id": fixture.get("base_scenario_id", fixture["scenario_id"]),
        "split": fixture.get("split", "pilot"),
        "memory_condition": fixture.get("memory_condition", "unlabeled"),
        "consequence_level": fixture.get("consequence_level", "unlabeled"),
        "dependence_type": fixture.get("dependence_type", "unlabeled"),
        "task_family": task_family,
        "policy": policy,
        "model": planner.model,
        "temperature": planner.temperature,
        "thinking": planner.thinking,
        "paired_samples": samples if policy in MEMIMPACT_POLICIES else 1,
        "verification_budget": verification_budget,
        "planner_attempts": sum(trace["attempt_count"] for trace in traces),
        "initial_action": initial_action.model_dump(),
        "baseline_flip_rate": baseline_flip,
        "flipped_memory_ids": flipped_memory_ids,
        "ranked_memory_ids": ranked_memory_ids,
        "selected_memory_ids": [memory.memory_id for memory in selected_memories],
        "verification_results": verification_results,
        "decision": decision,
        "final_action": final_action.model_dump(),
        "execution": execution,
        "lookup_execution": lookup_execution,
        "task_success": bool(execution and execution["task_success"]),
        "harmful_execution": bool(execution and execution["harmful_execution"]),
        "abstained": decision == "abstain",
        "planner_calls": len(traces),
        "memory_verification_calls": len(verification_results),
        "lookup_calls": int(lookup_execution is not None),
        "verification_calls": len(verification_results)
        + int(lookup_execution is not None),
        "tool_calls": int(execution is not None) + int(lookup_execution is not None),
        "planner_latency_ms": round(
            sum(trace["latency_ms"] for trace in traces), 3
        ),
        "planner_token_usage": total_usage,
        "comparisons": comparisons,
    }
    return result, traces
