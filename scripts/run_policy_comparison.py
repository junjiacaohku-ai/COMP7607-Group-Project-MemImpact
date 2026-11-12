import argparse
import datetime
import json
from pathlib import Path

from memimpact.core import MemoryRecord, remove_memory
from memimpact.episode import MEMIMPACT_POLICIES, POLICIES, run_episode
from memimpact.planner import TOOL_REGISTRY, CandidatePlanner, PlannerError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def summarize_policy(rows: list[dict]) -> dict:
    return {
        "episodes": len(rows),
        "task_success_rate": sum(row["task_success"] for row in rows) / len(rows),
        "harmful_execution_rate": sum(row["harmful_execution"] for row in rows)
        / len(rows),
        "abstention_rate": sum(row["abstained"] for row in rows) / len(rows),
        "verification_calls": sum(row["verification_calls"] for row in rows),
        "memory_verification_calls": sum(
            row.get("memory_verification_calls", row["verification_calls"])
            for row in rows
        ),
        "lookup_calls": sum(row.get("lookup_calls", 0) for row in rows),
        "tool_calls": sum(row.get("tool_calls", 0) for row in rows),
        "planner_calls": sum(row["planner_calls"] for row in rows),
        "planner_attempts": sum(row["planner_attempts"] for row in rows),
        "total_tokens": sum(
            row["planner_token_usage"]["total_tokens"] for row in rows
        ),
        "planner_latency_ms": round(
            sum(row["planner_latency_ms"] for row in rows), 3
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare MemImpact and baseline policies on matched scenarios"
    )
    parser.add_argument("--scenarios", nargs="+", type=Path)
    parser.add_argument("--policies", nargs="+", choices=POLICIES, default=POLICIES)
    parser.add_argument("--model", default="qwen3.8-flash")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--verification-budget", type=int, default=1)
    parser.add_argument("--max-planner-attempts", type=int, default=2)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "results" / "policy_comparison"
    )
    args = parser.parse_args()
    scenario_paths = args.scenarios or sorted(
        (PROJECT_ROOT / "benchmark" / "dev").glob("dev_*.json")
    )
    if not scenario_paths:
        raise ValueError("No scenarios found")

    planner = CandidatePlanner(
        args.model,
        args.temperature,
        thinking=not args.disable_thinking,
        max_attempts=args.max_planner_attempts,
    )
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_directory = args.output_dir / timestamp
    rows = []
    for scenario_path in scenario_paths:
        fixture = json.loads(scenario_path.read_text(encoding="utf-8"))
        memories = [MemoryRecord(**memory) for memory in fixture["memories"]]
        unknown_tools = set(fixture["available_tools"]) - set(TOOL_REGISTRY)
        if unknown_tools:
            raise ValueError(f"Unknown tools: {sorted(unknown_tools)}")
        shared_directory = run_directory / fixture["scenario_id"] / "shared_full"
        shared_directory.mkdir(parents=True, exist_ok=True)
        cached_full_runs = []
        try:
            for sample_index in range(args.samples):
                action, trace = planner.plan(
                    fixture["user_prompt"],
                    memories=memories,
                    tool_names=fixture["available_tools"],
                )
                trace.update(
                    {
                        "condition": "full",
                        "removed_memory_id": None,
                        "sample_index": sample_index,
                    }
                )
                cached_full_runs.append((action, trace))
        except PlannerError as error:
            (shared_directory / "failed_trace.json").write_text(
                json.dumps(error.trace, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            raise
        (shared_directory / "trace.json").write_text(
            json.dumps(
                [trace for _, trace in cached_full_runs], indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        cached_ablated_runs = None
        if any(policy in MEMIMPACT_POLICIES for policy in args.policies):
            cached_ablated_runs = {}
            ablated_directory = run_directory / fixture["scenario_id"] / "shared_ablated"
            ablated_directory.mkdir(parents=True, exist_ok=True)
            for memory in memories:
                remaining = remove_memory(memories, memory.memory_id)
                ablated_runs = []
                try:
                    for sample_index in range(args.samples):
                        action, trace = planner.plan(
                            fixture["user_prompt"],
                            memories=remaining,
                            tool_names=fixture["available_tools"],
                        )
                        trace.update(
                            {
                                "condition": "single_memory_removed",
                                "removed_memory_id": memory.memory_id,
                                "sample_index": sample_index,
                            }
                        )
                        ablated_runs.append((action, trace))
                except PlannerError as error:
                    (ablated_directory / "failed_trace.json").write_text(
                        json.dumps(error.trace, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    raise
                cached_ablated_runs[memory.memory_id] = ablated_runs
            (ablated_directory / "trace.json").write_text(
                json.dumps(
                    [
                        trace
                        for ablated_runs in cached_ablated_runs.values()
                        for _, trace in ablated_runs
                    ],
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        for policy in args.policies:
            output_directory = run_directory / fixture["scenario_id"] / policy
            output_directory.mkdir(parents=True, exist_ok=True)
            print(f"Running {fixture['scenario_id']} with {policy}", flush=True)
            result, traces = run_episode(
                fixture,
                policy,
                planner,
                args.samples,
                output_directory,
                args.verification_budget,
                cached_full_runs,
                cached_ablated_runs,
            )
            (output_directory / "result_summary.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (output_directory / "trace.json").write_text(
                json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            rows.append(result)

    comparison = {
        "model": args.model,
        "temperature": args.temperature,
        "thinking": not args.disable_thinking,
        "paired_samples": args.samples,
        "verification_budget": args.verification_budget,
        "cost_semantics": (
            "Per-policy costs are logical deployed costs. Shared cached calls are "
            "counted for each policy and do not represent total batch API spend."
        ),
        "scenarios": [path.name for path in scenario_paths],
        "by_policy": {
            policy: summarize_policy(
                [row for row in rows if row["policy"] == policy]
            )
            for policy in args.policies
        },
        "episodes": rows,
    }
    run_directory.mkdir(parents=True, exist_ok=True)
    (run_directory / "comparison_summary.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(comparison["by_policy"], indent=2, ensure_ascii=False))
    print(f"Saved comparison to {run_directory}")


if __name__ == "__main__":
    main()
