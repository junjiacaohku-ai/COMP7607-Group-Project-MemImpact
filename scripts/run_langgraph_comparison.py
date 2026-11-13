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


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cached_runs(
    path: Path,
    memories: list[MemoryRecord],
    removed_memory_id: str | None,
) -> dict[int, tuple[object, dict]]:
    if not path.exists():
        return {}
    expected_ids = [
        memory.memory_id
        for memory in memories
        if memory.memory_id != removed_memory_id
    ]
    expected_condition = (
        "full" if removed_memory_id is None else "single_memory_removed"
    )
    runs = {}
    for trace in json.loads(path.read_text(encoding="utf-8")):
        if (
            removed_memory_id is not None
            and trace.get("removed_memory_id") != removed_memory_id
        ):
            continue
        if (
            trace.get("condition") != expected_condition
            or trace.get("removed_memory_id") != removed_memory_id
            or trace.get("visible_memory_ids") != expected_ids
            or trace.get("planner_prompt_sha256") != PLANNER_PROMPT_SHA256
        ):
            raise ValueError(f"Incompatible cached planner trace: {path}")
        sample_index = trace.get("sample_index")
        if not isinstance(sample_index, int) or sample_index in runs:
            raise ValueError(f"Invalid or duplicate cached sample index: {path}")
        if trace.get("action") is None:
            raise ValueError(f"Cached planner trace has no action: {path}")
        from memimpact.core import CandidateAction

        runs[sample_index] = (CandidateAction(**trace["action"]), trace)
    return runs


def complete_cached_runs(
    runs: dict[int, tuple[object, dict]], samples: int
) -> list[tuple[object, dict]]:
    if set(runs) != set(range(samples)):
        raise ValueError("Cached planner runs are incomplete")
    return [runs[index] for index in range(samples)]


def save_failed_trace(directory: Path, error: SchemaPlannerError) -> None:
    path = directory / "failed_trace.json"
    if path.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = directory / f"failed_trace_retry_{timestamp}.json"
    write_json(path, error.trace)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a frozen comparison with LangGraph and ToolSandbox worker"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", type=Path, help="Existing run directory to resume")
    args = parser.parse_args()
    if args.resume and args.output_dir:
        parser.error("--resume cannot be combined with --output-dir")

    config = load_experiment_config(args.config)
    scenario_paths = config.scenario_paths(PROJECT_ROOT)
    actual_toolsandbox_sha = git_revision(TOOLSANDBOX_ROOT)
    if actual_toolsandbox_sha != config.toolsandbox_git_sha:
        raise RuntimeError("ToolSandbox revision does not match the frozen config")

    planner = SchemaCandidatePlanner(
        config.model,
        config.temperature,
        thinking=config.thinking,
        max_attempts=config.max_planner_attempts,
    )
    resolved_config = config.model_dump()
    config_sha = hashlib.sha256(
        json.dumps(resolved_config, sort_keys=True).encode()
    ).hexdigest()
    tool_schema_sha = hashlib.sha256(TOOL_SCHEMA_PATH.read_bytes()).hexdigest()
    if args.resume:
        run_directory = args.resume
        metadata_path = run_directory / "run_metadata.json"
        if not metadata_path.exists():
            raise ValueError(f"Cannot resume without metadata: {metadata_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected = {
            "runtime": "langgraph",
            "config_sha256": config_sha,
            "planner_prompt_sha256": PLANNER_PROMPT_SHA256,
            "tool_schema_sha256": tool_schema_sha,
            "toolsandbox_git_sha": actual_toolsandbox_sha,
        }
        mismatches = [
            key for key, value in expected.items() if metadata.get(key) != value
        ]
        if mismatches:
            raise ValueError(f"Resume metadata mismatch: {', '.join(mismatches)}")
    else:
        output_base = args.output_dir or PROJECT_ROOT / config.output_dir
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_directory = output_base / f"{config.config_id}_langgraph_{timestamp}"
        run_directory.mkdir(parents=True, exist_ok=False)
        metadata = {
            "runtime": "langgraph",
            "langgraph_version": version("langgraph"),
            "resolved_config": resolved_config,
            "config_sha256": config_sha,
            "planner_prompt_sha256": PLANNER_PROMPT_SHA256,
            "tool_schema_sha256": tool_schema_sha,
            "project_git_sha": git_revision(PROJECT_ROOT),
            "project_has_uncommitted_changes": subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "diff", "--quiet"], check=False
            ).returncode
            != 0,
            "toolsandbox_git_sha": actual_toolsandbox_sha,
        }
        write_json(run_directory / "run_metadata.json", metadata)

    if args.resume:
        history_path = run_directory / "resume_history.json"
        history = (
            json.loads(history_path.read_text(encoding="utf-8"))
            if history_path.exists()
            else []
        )
        history.append(
            {
                "resumed_at": datetime.datetime.now().isoformat(),
                "project_git_sha": git_revision(PROJECT_ROOT),
                "project_has_uncommitted_changes": subprocess.run(
                    ["git", "-C", str(PROJECT_ROOT), "diff", "--quiet"], check=False
                ).returncode
                != 0,
            }
        )
        write_json(history_path, history)

    rows = []
    executor = ToolSandboxProcessExecutor()
    for scenario_path in scenario_paths:
        fixture = json.loads(scenario_path.read_text(encoding="utf-8"))
        memories = [MemoryRecord(**memory) for memory in fixture["memories"]]
        unknown_tools = set(fixture["available_tools"]) - set(planner.tool_schemas)
        if unknown_tools:
            raise ValueError(f"Unknown tools: {sorted(unknown_tools)}")

        saved_results = {}
        for policy in config.policies:
            policy_directory = run_directory / fixture["scenario_id"] / policy
            result_path = policy_directory / "result_summary.json"
            trace_path = policy_directory / "trace.json"
            if result_path.exists() and trace_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                traces = json.loads(trace_path.read_text(encoding="utf-8"))
                if (
                    result.get("scenario_id") != fixture["scenario_id"]
                    or result.get("policy") != policy
                    or not isinstance(traces, list)
                ):
                    raise ValueError(f"Invalid saved policy result: {result_path}")
                saved_results[policy] = result
        if len(saved_results) == len(config.policies):
            rows.extend(saved_results[policy] for policy in config.policies)
            print(f"Reusing completed {fixture['scenario_id']}", flush=True)
            continue

        shared_directory = run_directory / fixture["scenario_id"] / "shared_full"
        shared_directory.mkdir(parents=True, exist_ok=True)
        full_trace_path = shared_directory / "trace.json"
        full_runs = load_cached_runs(full_trace_path, memories, None)
        try:
            for sample_index in range(config.samples):
                if sample_index in full_runs:
                    continue
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
                full_runs[sample_index] = (action, trace)
                write_json(
                    full_trace_path,
                    [full_runs[index][1] for index in sorted(full_runs)],
                )
        except SchemaPlannerError as error:
            save_failed_trace(shared_directory, error)
            raise
        cached_full_runs = complete_cached_runs(full_runs, config.samples)

        cached_ablated_runs = None
        if any(policy in MEMIMPACT_POLICIES for policy in config.policies):
            cached_ablated_runs = {}
            ablated_directory = run_directory / fixture["scenario_id"] / "shared_ablated"
            ablated_directory.mkdir(parents=True, exist_ok=True)
            ablated_trace_path = ablated_directory / "trace.json"
            for memory in memories:
                remaining = remove_memory(memories, memory.memory_id)
                ablated_runs = load_cached_runs(
                    ablated_trace_path, memories, memory.memory_id
                )
                try:
                    for sample_index in range(config.samples):
                        if sample_index in ablated_runs:
                            continue
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
                        ablated_runs[sample_index] = (action, trace)
                        write_json(
                            ablated_trace_path,
                            [
                                trace
                                for runs in cached_ablated_runs.values()
                                for _, trace in runs
                            ]
                            + [
                                ablated_runs[index][1]
                                for index in sorted(ablated_runs)
                            ],
                        )
                except SchemaPlannerError as error:
                    save_failed_trace(ablated_directory, error)
                    raise
                cached_ablated_runs[memory.memory_id] = complete_cached_runs(
                    ablated_runs, config.samples
                )
                write_json(
                    ablated_trace_path,
                    [
                        trace
                        for runs in cached_ablated_runs.values()
                        for _, trace in runs
                    ],
                )

        for policy in config.policies:
            if policy in saved_results:
                rows.append(saved_results[policy])
                print(
                    f"Reusing {fixture['scenario_id']} with {policy}", flush=True
                )
                continue
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
            write_json(output_directory / "result_summary.json", result)
            write_json(output_directory / "trace.json", traces)
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
