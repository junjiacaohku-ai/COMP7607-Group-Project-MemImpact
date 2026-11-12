import argparse
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

from memimpact.config import load_experiment_config
from memimpact.core import MemoryRecord, remove_memory
from memimpact.episode import MEMIMPACT_POLICIES, POLICIES, run_episode
from memimpact.planner import (
    PLANNER_PROMPT_SHA256,
    TOOL_REGISTRY,
    CandidatePlanner,
    PlannerError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLSANDBOX_ROOT = PROJECT_ROOT / "third_party" / "ToolSandbox"


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


def git_revision(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare MemImpact and baseline policies on matched scenarios"
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--scenarios", nargs="+", type=Path)
    parser.add_argument("--policies", nargs="+", choices=POLICIES)
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--verification-budget", type=int)
    parser.add_argument("--max-planner-attempts", type=int)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    config = load_experiment_config(args.config) if args.config else None

    def setting(name, current, default):
        if current is not None:
            return current
        if config is not None:
            return getattr(config, name)
        return default

    model = setting("model", args.model, "qwen3.8-flash")
    temperature = setting("temperature", args.temperature, 0.0)
    samples = setting("samples", args.samples, 3)
    verification_budget = setting(
        "verification_budget", args.verification_budget, 1
    )
    max_attempts = setting(
        "max_planner_attempts", args.max_planner_attempts, 2
    )
    thinking = setting("thinking", None, True) and not args.disable_thinking
    policies = args.policies or (config.policies if config else list(POLICIES))
    scenario_paths = (
        args.scenarios
        or (config.scenario_paths(PROJECT_ROOT) if config else None)
        or sorted((PROJECT_ROOT / "benchmark" / "dev").glob("dev_*.json"))
    )
    if not scenario_paths:
        raise ValueError("No scenarios found")
    output_base = args.output_dir or PROJECT_ROOT / setting(
        "output_dir", None, "results/policy_comparison"
    )

    actual_toolsandbox_sha = git_revision(TOOLSANDBOX_ROOT)
    if config and actual_toolsandbox_sha != config.toolsandbox_git_sha:
        raise RuntimeError("ToolSandbox revision does not match the frozen config")

    planner = CandidatePlanner(
        model,
        temperature,
        thinking=thinking,
        max_attempts=max_attempts,
    )
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    config_prefix = f"{config.config_id}_" if config else ""
    run_directory = output_base / f"{config_prefix}{timestamp}"
    run_directory.mkdir(parents=True, exist_ok=True)
    resolved_config = (
        config.model_dump()
        if config
        else {
            "config_id": "ad_hoc",
            "status": "development",
            "frozen": False,
            "model": model,
            "temperature": temperature,
            "samples": samples,
            "thinking": thinking,
            "verification_budget": verification_budget,
            "max_planner_attempts": max_attempts,
            "policies": policies,
            "scenarios": [str(path) for path in scenario_paths],
            "output_dir": str(output_base),
        }
    )
    config_sha = hashlib.sha256(
        json.dumps(resolved_config, sort_keys=True).encode()
    ).hexdigest()
    metadata = {
        "resolved_config": resolved_config,
        "config_sha256": config_sha,
        "planner_prompt_sha256": PLANNER_PROMPT_SHA256,
        "project_git_sha": git_revision(PROJECT_ROOT),
        "project_has_uncommitted_changes": subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "diff", "--quiet"], check=False
        ).returncode
        != 0,
        "toolsandbox_git_sha": actual_toolsandbox_sha,
    }
    (run_directory / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

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
            for sample_index in range(samples):
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
        if any(policy in MEMIMPACT_POLICIES for policy in policies):
            cached_ablated_runs = {}
            ablated_directory = run_directory / fixture["scenario_id"] / "shared_ablated"
            ablated_directory.mkdir(parents=True, exist_ok=True)
            for memory in memories:
                remaining = remove_memory(memories, memory.memory_id)
                ablated_runs = []
                try:
                    for sample_index in range(samples):
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
        for policy in policies:
            output_directory = run_directory / fixture["scenario_id"] / policy
            output_directory.mkdir(parents=True, exist_ok=True)
            print(f"Running {fixture['scenario_id']} with {policy}", flush=True)
            result, traces = run_episode(
                fixture,
                policy,
                planner,
                samples,
                output_directory,
                verification_budget,
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
        "config_id": config.config_id if config else "ad_hoc",
        "status": config.status if config else "development",
        "frozen": config.frozen if config else False,
        "config_sha256": config_sha,
        "planner_prompt_sha256": PLANNER_PROMPT_SHA256,
        "project_git_sha": metadata["project_git_sha"],
        "toolsandbox_git_sha": actual_toolsandbox_sha,
        "model": model,
        "temperature": temperature,
        "thinking": thinking,
        "paired_samples": samples,
        "verification_budget": verification_budget,
        "bootstrap_resamples": setting("bootstrap_resamples", None, 2000),
        "bootstrap_seed": setting("bootstrap_seed", None, 42),
        "cost_semantics": (
            "Per-policy costs are logical deployed costs. Shared cached calls are "
            "counted for each policy and do not represent total batch API spend."
        ),
        "scenarios": [path.name for path in scenario_paths],
        "by_policy": {
            policy: summarize_policy([row for row in rows if row["policy"] == policy])
            for policy in policies
        },
        "episodes": rows,
    }
    (run_directory / "comparison_summary.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(comparison["by_policy"], indent=2, ensure_ascii=False))
    print(f"Saved comparison to {run_directory}")


if __name__ == "__main__":
    main()
