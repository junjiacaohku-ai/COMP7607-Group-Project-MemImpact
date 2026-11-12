import argparse
import datetime
import hashlib
import json
import subprocess
from importlib.metadata import version
from pathlib import Path

from memimpact.config import load_experiment_config
from memimpact.core import MemoryRecord, remove_memory
from memimpact.experiment import git_revision, summarize_policy
from memimpact.langgraph_runtime import run_langgraph_episode
from memimpact.policies import MEMIMPACT_POLICIES
from memimpact.process_adapter import ToolSandboxProcessExecutor
from memimpact.prompts import PLANNER_PROMPT_SHA256
from memimpact.schema_planner import SchemaCandidatePlanner, SchemaPlannerError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLSANDBOX_ROOT = PROJECT_ROOT / "third_party" / "ToolSandbox"
TOOL_SCHEMA_PATH = PROJECT_ROOT / "configs" / "toolsandbox_tools.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a frozen comparison with LangGraph and ToolSandbox worker"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    config = load_experiment_config(args.config)
    scenario_paths = config.scenario_paths(PROJECT_ROOT)
    output_base = args.output_dir or PROJECT_ROOT / config.output_dir
    actual_toolsandbox_sha = git_revision(TOOLSANDBOX_ROOT)
    if actual_toolsandbox_sha != config.toolsandbox_git_sha:
        raise RuntimeError("ToolSandbox revision does not match the frozen config")

    planner = SchemaCandidatePlanner(
        config.model,
        config.temperature,
        thinking=config.thinking,
        max_attempts=config.max_planner_attempts,
    )
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_directory = output_base / f"{config.config_id}_langgraph_{timestamp}"
    run_directory.mkdir(parents=True, exist_ok=True)
    resolved_config = config.model_dump()
    config_sha = hashlib.sha256(
        json.dumps(resolved_config, sort_keys=True).encode()
    ).hexdigest()
    metadata = {
        "runtime": "langgraph",
        "langgraph_version": version("langgraph"),
        "resolved_config": resolved_config,
        "config_sha256": config_sha,
        "planner_prompt_sha256": PLANNER_PROMPT_SHA256,
        "tool_schema_sha256": hashlib.sha256(TOOL_SCHEMA_PATH.read_bytes()).hexdigest(),
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
    executor = ToolSandboxProcessExecutor()
    for scenario_path in scenario_paths:
        fixture = json.loads(scenario_path.read_text(encoding="utf-8"))
        memories = [MemoryRecord(**memory) for memory in fixture["memories"]]
        unknown_tools = set(fixture["available_tools"]) - set(planner.tool_schemas)
        if unknown_tools:
            raise ValueError(f"Unknown tools: {sorted(unknown_tools)}")
        shared_directory = run_directory / fixture["scenario_id"] / "shared_full"
        shared_directory.mkdir(parents=True, exist_ok=True)
        cached_full_runs = []
        try:
            for sample_index in range(config.samples):
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
        except SchemaPlannerError as error:
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
        if any(policy in MEMIMPACT_POLICIES for policy in config.policies):
            cached_ablated_runs = {}
            ablated_directory = run_directory / fixture["scenario_id"] / "shared_ablated"
            ablated_directory.mkdir(parents=True, exist_ok=True)
            for memory in memories:
                remaining = remove_memory(memories, memory.memory_id)
                ablated_runs = []
                try:
                    for sample_index in range(config.samples):
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
                except SchemaPlannerError as error:
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

        for policy in config.policies:
            output_directory = run_directory / fixture["scenario_id"] / policy
            output_directory.mkdir(parents=True, exist_ok=True)
            print(f"Running {fixture['scenario_id']} with {policy}", flush=True)
            result, traces = run_langgraph_episode(
                fixture,
                policy,
                planner,
                config.samples,
                executor,
                verification_budget=config.verification_budget,
                cached_full_runs=cached_full_runs,
                cached_ablated_runs=cached_ablated_runs,
            )
            (output_directory / "result_summary.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (output_directory / "trace.json").write_text(
                json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            rows.append(result)

    comparison = {
        "config_id": config.config_id,
        "status": config.status,
        "frozen": config.frozen,
        "runtime": "langgraph",
        "langgraph_version": metadata["langgraph_version"],
        "config_sha256": config_sha,
        "planner_prompt_sha256": PLANNER_PROMPT_SHA256,
        "tool_schema_sha256": metadata["tool_schema_sha256"],
        "project_git_sha": metadata["project_git_sha"],
        "toolsandbox_git_sha": actual_toolsandbox_sha,
        "model": config.model,
        "temperature": config.temperature,
        "thinking": config.thinking,
        "paired_samples": config.samples,
        "verification_budget": config.verification_budget,
        "max_planner_attempts": config.max_planner_attempts,
        "bootstrap_resamples": config.bootstrap_resamples,
        "bootstrap_seed": config.bootstrap_seed,
        "cost_semantics": (
            "Per-policy costs are logical deployed costs. Shared cached calls are "
            "counted for each policy and do not represent total batch API spend."
        ),
        "scenarios": [path.name for path in scenario_paths],
        "by_policy": {
            policy: summarize_policy(
                [row for row in rows if row["policy"] == policy]
            )
            for policy in config.policies
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
