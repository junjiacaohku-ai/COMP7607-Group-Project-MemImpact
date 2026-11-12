import argparse
import json
from pathlib import Path

from memimpact.core import CandidateAction
from memimpact.episode import run_episode
from memimpact.planner import CandidatePlanner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIRECTORIES = (
    "benchmark/dev",
    "benchmark/reminder_pilot",
    "benchmark/deletion_pilot",
    "scenarios/pilot",
)


def scenario_path(filename: str) -> Path:
    for directory in SCENARIO_DIRECTORIES:
        path = PROJECT_ROOT / directory / filename
        if path.exists():
            return path
    raise FileNotFoundError(f"Cannot locate scenario fixture: {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate offline verification-critical memory labels for a comparison run"
    )
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    comparison_path = args.run_directory / "comparison_summary.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    planner = CandidatePlanner(
        comparison["model"],
        comparison["temperature"],
        thinking=comparison["thinking"],
        max_attempts=comparison.get("max_planner_attempts", 2),
    )

    scenario_references = dict.fromkeys(comparison["scenarios"])
    label_counts = []
    for scenario_reference in scenario_references:
        fixture = json.loads(
            scenario_path(scenario_reference).read_text(encoding="utf-8")
        )
        scenario_id = fixture["scenario_id"]
        scenario_directory = args.run_directory / scenario_id
        shared_traces = json.loads(
            (scenario_directory / "shared_full" / "trace.json").read_text(
                encoding="utf-8"
            )
        )
        cached_full = [
            (CandidateAction(**trace["action"]), trace) for trace in shared_traces
        ][:1]
        baseline, _ = run_episode(
            fixture,
            "always_proceed",
            planner,
            1,
            scenario_directory / "offline_labels" / "baseline",
            cached_full_runs=cached_full,
        )
        memory_results = []
        for memory in fixture["memories"]:
            output_directory = (
                scenario_directory
                / "offline_labels"
                / memory["memory_id"]
            )
            result, traces = run_episode(
                fixture,
                "always_proceed",
                planner,
                1,
                output_directory,
                cached_full_runs=cached_full,
                forced_memory_id=memory["memory_id"],
            )
            critical = (
                (not baseline["task_success"] or baseline["harmful_execution"])
                and result["task_success"]
                and not result["harmful_execution"]
            )
            additional_traces = [
                trace for trace in traces if trace["condition"] != "full"
            ]
            memory_results.append(
                {
                    "memory_id": memory["memory_id"],
                    "verification": result["verification_results"],
                    "task_success_after_verification": result["task_success"],
                    "harmful_execution_after_verification": result[
                        "harmful_execution"
                    ],
                    "critical": critical,
                    "offline_planner_calls": len(additional_traces),
                    "offline_planner_attempts": sum(
                        trace["attempt_count"] for trace in additional_traces
                    ),
                    "offline_tokens": sum(
                        trace["usage"]["total_tokens"] for trace in additional_traces
                    ),
                }
            )
            output_directory.mkdir(parents=True, exist_ok=True)
            (output_directory / "trace.json").write_text(
                json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        labels = {
            "scenario_id": scenario_id,
            "definition": (
                "Verifying this memory turns the shared initial failed or harmful "
                "outcome into a successful outcome without harmful execution"
            ),
            "baseline": {
                "task_success": baseline["task_success"],
                "harmful_execution": baseline["harmful_execution"],
            },
            "critical_memory_ids": [
                item["memory_id"] for item in memory_results if item["critical"]
            ],
            "memories": memory_results,
            "offline_planner_attempts": sum(
                item["offline_planner_attempts"] for item in memory_results
            ),
            "offline_tokens": sum(
                item["offline_tokens"] for item in memory_results
            ),
            "cost_semantics": "Offline label-generation costs are separate from online policy costs",
        }
        (scenario_directory / "critical_labels.json").write_text(
            json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        label_counts.append(
            {
                "scenario_id": scenario_id,
                "critical_memory_ids": labels["critical_memory_ids"],
            }
        )
        print(json.dumps(label_counts[-1], ensure_ascii=False), flush=True)
    print(f"Saved offline critical-memory labels in {args.run_directory}")


if __name__ == "__main__":
    main()
