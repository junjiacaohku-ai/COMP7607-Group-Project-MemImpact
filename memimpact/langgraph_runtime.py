import copy
import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from memimpact.core import (
    CandidateAction,
    MemoryRecord,
    action_flip_rate,
    baseline_flip_rate,
    noise_adjusted_impact,
    remove_memory,
)
from memimpact.policies import MEMIMPACT_POLICIES, POLICIES
from memimpact.scoring import observable_uncertainty, verification_score
from memimpact.verification import AuthoritativeContactVerifier


class GraphState(TypedDict, total=False):
    fixture: dict[str, Any]
    policy: str
    memories: list[MemoryRecord]
    initial_action: CandidateAction
    final_action: CandidateAction
    full_actions: list[CandidateAction]
    baseline_flip_rate: float | None
    comparisons: list[dict[str, Any]]
    traces: Annotated[list[dict[str, Any]], operator.add]
    selected_memories: list[MemoryRecord]
    verification_results: list[dict[str, Any]]
    verified_evidence: list[dict[str, Any]]
    decision: str
    needs_replan: bool
    replan_reason: str | None
    replan_count: int
    execution: dict[str, Any] | None
    lookup_execution: dict[str, Any] | None
    lookup_calls: int
    lookup_field: str | None
    lookup_values: list[Any]


def candidate_conditioned_memories(
    memories: list[MemoryRecord], action: CandidateAction
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


def run_langgraph_episode(
    fixture: dict[str, Any],
    policy: str,
    planner: Any,
    samples: int,
    executor: Any,
    verification_budget: int = 1,
    cached_full_runs: list[tuple[CandidateAction, dict[str, Any]]] | None = None,
    cached_ablated_runs: dict[str, list[tuple[CandidateAction, dict[str, Any]]]]
    | None = None,
    forced_memory_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")
    if samples < 1 or verification_budget < 0:
        raise ValueError("samples must be positive and verification_budget non-negative")

    memories = [MemoryRecord(**memory) for memory in fixture["memories"]]
    verifier = AuthoritativeContactVerifier(
        fixture.get("authoritative_contacts", []),
        fixture.get("verification_overrides"),
    )
    task_family = fixture.get("task_family", "messaging")
    if task_family == "messaging":
        target_tool = "send_message_with_phone_number"
        lookup_tools = {"search_contacts"}
        lookup_field = "phone_number"
        critical_scopes = {"contact"}
    else:
        target_tool = (
            "add_reminder" if task_family == "reminder_creation" else "remove_reminder"
        )
        lookup_tools = {"search_reminder"}
        lookup_field = (
            "reminder_timestamp"
            if task_family == "reminder_creation"
            else "reminder_id"
        )
        critical_scopes = {"reminder", "reminder_time", "reminder_target"}

    def plan_full(state: GraphState) -> GraphState:
        runs = []
        traces = []
        count = samples if policy in MEMIMPACT_POLICIES else 1
        if cached_full_runs is None:
            for sample_index in range(count):
                action, trace = planner.plan(
                    fixture["user_prompt"], memories, fixture["available_tools"]
                )
                trace.update(
                    {
                        "condition": "full",
                        "removed_memory_id": None,
                        "sample_index": sample_index,
                    }
                )
                runs.append(action)
                traces.append(trace)
        else:
            if len(cached_full_runs) < count:
                raise ValueError("Not enough cached full-memory runs")
            for action, trace in cached_full_runs[:count]:
                cached_trace = copy.deepcopy(trace)
                cached_trace["shared_across_policies"] = True
                runs.append(action)
                traces.append(cached_trace)
        return {
            "full_actions": runs,
            "initial_action": runs[0],
            "final_action": runs[0],
            "baseline_flip_rate": (
                baseline_flip_rate(runs) if policy in MEMIMPACT_POLICIES else None
            ),
            "traces": traces,
        }

    def audit(state: GraphState) -> GraphState:
        if policy not in MEMIMPACT_POLICIES:
            return {}
        comparisons = []
        traces = []
        for memory in memories:
            remaining = remove_memory(memories, memory.memory_id)
            ablated_actions = []
            if cached_ablated_runs is None:
                for sample_index in range(samples):
                    action, trace = planner.plan(
                        fixture["user_prompt"], remaining, fixture["available_tools"]
                    )
                    trace.update(
                        {
                            "condition": "single_memory_removed",
                            "removed_memory_id": memory.memory_id,
                            "sample_index": sample_index,
                        }
                    )
                    ablated_actions.append(action)
                    traces.append(trace)
            else:
                cached_runs = cached_ablated_runs[memory.memory_id]
                if len(cached_runs) < samples:
                    raise ValueError("Not enough cached ablated runs")
                for action, trace in cached_runs[:samples]:
                    cached_trace = copy.deepcopy(trace)
                    cached_trace["shared_across_policies"] = True
                    ablated_actions.append(action)
                    traces.append(cached_trace)
            raw_flip = action_flip_rate(state["full_actions"], ablated_actions)
            impact = noise_adjusted_impact(raw_flip, state["baseline_flip_rate"])
            uncertainty = observable_uncertainty(
                memory, fixture.get("current_time", "2026-01-01T00:00:00+08:00")
            )
            score = (
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
                    "baseline_flip_rate": state["baseline_flip_rate"],
                    "noise_adjusted_impact": impact,
                    "observable_uncertainty": uncertainty,
                    "selection_score": score,
                }
            )
        return {"comparisons": comparisons, "traces": traces}

    def select(state: GraphState) -> GraphState:
        if forced_memory_id is not None:
            selected = [
                memory for memory in memories if memory.memory_id == forced_memory_id
            ]
            if len(selected) != 1:
                raise ValueError(f"Unknown forced memory: {forced_memory_id}")
        elif policy == "always_proceed":
            selected = []
        elif policy == "always_verify":
            selected = memories
        elif policy == "static":
            selected = sorted(
                (
                    memory
                    for memory in memories
                    if memory.scope in critical_scopes
                ),
                key=lambda memory: memory.timestamp,
            )[:verification_budget]
        elif policy == "amv_guard":
            selected = candidate_conditioned_memories(
                memories, state["initial_action"]
            )[:verification_budget]
        else:
            ranked = [
                item["removed_memory_id"]
                for item in sorted(
                    state["comparisons"],
                    key=lambda item: item["selection_score"],
                    reverse=True,
                )
                if item["selection_score"] > 0
            ]
            by_id = {memory.memory_id: memory for memory in memories}
            selected = [
                by_id[memory_id] for memory_id in ranked[:verification_budget]
            ]
        return {"selected_memories": selected}

    def verify(state: GraphState) -> GraphState:
        results = []
        evidence = []
        unresolved = False
        for memory in state["selected_memories"]:
            result = verifier.verify(memory)
            results.append(result.model_dump())
            if result.status == "refuted":
                evidence.append(result.evidence)
            elif result.status == "unknown" and memory.scope in critical_scopes:
                unresolved = True
        return {
            "verification_results": results,
            "verified_evidence": evidence,
            "needs_replan": bool(evidence),
            "replan_reason": "refutation" if evidence else None,
            "decision": "abstain" if unresolved and not evidence else "proceed",
        }

    def replan(state: GraphState) -> GraphState:
        if not state.get("needs_replan", False):
            return {}
        evidence = state.get("verified_evidence", [])
        reason = state.get("replan_reason", "refutation")
        action, trace = planner.plan(
            fixture["user_prompt"],
            memories,
            fixture["available_tools"],
            verified_evidence=evidence,
        )
        trace.update(
            {
                "condition": f"replan_after_{reason}",
                "removed_memory_id": None,
                "sample_index": None,
            }
        )
        decision = "proceed"
        verified_values = {
            key: {item[key] for item in evidence if key in item}
            for key in ("phone_number", "reminder_timestamp", "reminder_id")
        }
        if action.tool_name not in {target_tool, *lookup_tools}:
            decision = "abstain"
        elif action.tool_name == target_tool:
            for key, values in verified_values.items():
                if values and action.arguments.get(key) not in values:
                    decision = "abstain"
            if (
                reason == "lookup"
                and state.get("lookup_values")
                and action.arguments.get(state["lookup_field"])
                not in state["lookup_values"]
            ):
                decision = "abstain"
        return {
            "final_action": action,
            "decision": decision,
            "needs_replan": False,
            "replan_reason": None,
            "replan_count": state.get("replan_count", 0) + 1,
            "traces": [trace],
        }

    def execute(state: GraphState) -> GraphState:
        if state["decision"] == "abstain":
            return {}
        action = state["final_action"]
        if action.tool_name in lookup_tools:
            if state.get("replan_count", 0) >= 2:
                return {"decision": "abstain", "needs_replan": False}
            result = executor(action, fixture)
            records = result["tool_result"]
            if not records:
                return {"decision": "abstain", "needs_replan": False}
            evidence = {
                "type": "authoritative_tool_result",
                "tool_name": action.tool_name,
                "records": records,
            }
            return {
                "lookup_execution": result,
                "lookup_calls": state.get("lookup_calls", 0) + 1,
                "lookup_field": lookup_field,
                "lookup_values": [
                    record[lookup_field]
                    for record in records
                    if lookup_field in record
                ],
                "verified_evidence": [
                    *state.get("verified_evidence", []),
                    evidence,
                ],
                "needs_replan": True,
                "replan_reason": "lookup",
            }
        result = executor(action, fixture)
        return {"execution": result}

    graph = StateGraph(GraphState)
    graph.add_node("plan_full", plan_full)
    graph.add_node("audit", audit)
    graph.add_node("select", select)
    graph.add_node("verify", verify)
    graph.add_node("replan", replan)
    graph.add_node("execute", execute)
    graph.set_entry_point("plan_full")
    graph.add_edge("plan_full", "audit")
    graph.add_edge("audit", "select")
    graph.add_edge("select", "verify")
    graph.add_edge("verify", "replan")
    graph.add_edge("replan", "execute")
    graph.add_conditional_edges(
        "execute",
        lambda state: (
            "replan"
            if state.get("needs_replan", False) and state["decision"] == "proceed"
            else END
        ),
    )
    app = graph.compile()
    initial: GraphState = {
        "fixture": fixture,
        "policy": policy,
        "memories": memories,
        "full_actions": [],
        "comparisons": [],
        "traces": [],
        "verification_results": [],
        "verified_evidence": [],
        "decision": "proceed",
        "needs_replan": False,
        "replan_count": 0,
        "execution": None,
        "lookup_execution": None,
        "lookup_calls": 0,
        "baseline_flip_rate": None,
    }
    state = app.invoke(initial)
    traces = state["traces"]
    total_usage = {
        key: sum(trace["usage"][key] for trace in traces)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    execution = state.get("execution")
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
        "initial_action": state["initial_action"].model_dump(),
        "baseline_flip_rate": state["baseline_flip_rate"],
        "flipped_memory_ids": [
            item["removed_memory_id"]
            for item in state["comparisons"]
            if item["raw_action_flip_rate"] > 0
        ],
        "ranked_memory_ids": [
            item["removed_memory_id"]
            for item in sorted(
                state["comparisons"],
                key=lambda item: item["selection_score"],
                reverse=True,
            )
            if item["selection_score"] > 0
        ],
        "selected_memory_ids": [
            memory.memory_id for memory in state["selected_memories"]
        ],
        "verification_results": state["verification_results"],
        "decision": state["decision"],
        "final_action": state["final_action"].model_dump(),
        "execution": execution,
        "lookup_execution": state.get("lookup_execution"),
        "task_success": bool(execution and execution["task_success"]),
        "harmful_execution": bool(execution and execution["harmful_execution"]),
        "abstained": state["decision"] == "abstain",
        "planner_calls": len(traces),
        "memory_verification_calls": len(state["verification_results"]),
        "lookup_calls": state.get("lookup_calls", 0),
        "verification_calls": len(state["verification_results"])
        + state.get("lookup_calls", 0),
        "tool_calls": int(execution is not None) + state.get("lookup_calls", 0),
        "planner_latency_ms": round(
            sum(trace["latency_ms"] for trace in traces), 3
        ),
        "planner_token_usage": total_usage,
        "comparisons": state["comparisons"],
        "runtime": "langgraph",
        "langgraph_version": "1.2.20",
    }
    return result, traces
