import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

RATE_METRICS = {
    "task_success_rate": "task_success",
    "harmful_execution_rate": "harmful_execution",
    "abstention_rate": "abstained",
}
TOTAL_METRICS = {
    "verification_calls": "verification_calls",
    "total_tokens": "total_tokens",
    "planner_latency_ms": "planner_latency_ms",
}
BOOTSTRAP_METRICS = (
    "task_success",
    "harmful_execution",
    "abstained",
    "verification_calls",
    "total_tokens",
    "planner_latency_ms",
)
COMPATIBILITY_FIELDS = (
    "scenarios",
    "model",
    "temperature",
    "thinking",
    "paired_samples",
    "max_planner_attempts",
    "planner_prompt_sha256",
    "tool_schema_sha256",
    "toolsandbox_git_sha",
    "bootstrap_resamples",
    "bootstrap_seed",
)


def episode_key(row: dict[str, Any]) -> tuple[str, str]:
    return row["scenario_id"], row["policy"]


def metric_value(row: dict[str, Any], metric: str) -> float:
    if metric == "total_tokens":
        return float(row["planner_token_usage"]["total_tokens"])
    return float(row[metric])


def load_run(run_directory: Path) -> dict[str, Any]:
    data = json.loads(
        (run_directory / "comparison_summary.json").read_text(encoding="utf-8")
    )
    keys = [episode_key(row) for row in data["episodes"]]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Duplicate scenario-policy episodes: {run_directory}")
    return data


def validate_compatibility(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> None:
    mismatches = [
        field
        for field in COMPATIBILITY_FIELDS
        if reference.get(field) != candidate.get(field)
    ]
    if mismatches:
        raise ValueError(f"Run metadata mismatch: {', '.join(mismatches)}")
    reference_rows = {episode_key(row): row for row in reference["episodes"]}
    candidate_rows = {episode_key(row): row for row in candidate["episodes"]}
    if reference_rows.keys() != candidate_rows.keys():
        raise ValueError("Runs do not contain identical scenario-policy pairs")
    if list(reference["by_policy"]) != list(candidate["by_policy"]):
        raise ValueError("Policy order differs between runs")
    for key, reference_row in reference_rows.items():
        candidate_row = candidate_rows[key]
        reference_base = reference_row.get("base_scenario_id", key[0])
        candidate_base = candidate_row.get("base_scenario_id", key[0])
        if reference_base != candidate_base:
            raise ValueError(f"Base scenario mismatch for {key}")


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    result: dict[str, float | int] = {"episodes": len(rows)}
    for output_name, field in RATE_METRICS.items():
        result[output_name] = sum(bool(row[field]) for row in rows) / len(rows)
    for output_name, field in TOTAL_METRICS.items():
        result[output_name] = sum(metric_value(row, field) for row in rows)
    for field in TOTAL_METRICS.values():
        result[f"mean_{field}"] = sum(
            metric_value(row, field) for row in rows
        ) / len(rows)
    return result


def outcome_transitions(
    reference_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    transitions = {}
    for field in RATE_METRICS.values():
        transitions[field] = {
            "0_to_1": sum(
                not reference[field] and bool(candidate[field])
                for reference, candidate in zip(reference_rows, candidate_rows)
            ),
            "1_to_0": sum(
                bool(reference[field]) and not candidate[field]
                for reference, candidate in zip(reference_rows, candidate_rows)
            ),
            "unchanged": sum(
                bool(reference[field]) == bool(candidate[field])
                for reference, candidate in zip(reference_rows, candidate_rows)
            ),
        }
    return transitions


def budget_bootstrap(
    reference_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    policy: str,
    metric: str,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    grouped = defaultdict(list)
    for reference, candidate in zip(reference_rows, candidate_rows):
        scenario_id = reference["scenario_id"]
        base_id = reference.get("base_scenario_id", scenario_id)
        grouped[base_id].append(
            metric_value(candidate, metric) - metric_value(reference, metric)
        )
    groups = list(grouped.values())
    observed = sum(map(sum, groups)) / sum(map(len, groups))
    rng = random.Random(seed)
    bootstrap_values = []
    for _ in range(resamples):
        sampled_groups = [groups[rng.randrange(len(groups))] for _ in groups]
        flat = [value for group in sampled_groups for value in group]
        bootstrap_values.append(sum(flat) / len(flat))
    bootstrap_values.sort()
    lower_index = round(0.025 * (resamples - 1))
    upper_index = round(0.975 * (resamples - 1))
    return {
        "policy": policy,
        "metric": metric,
        "effect_definition": "candidate budget minus reference budget",
        "observed_difference": observed,
        "ci_95": [
            bootstrap_values[lower_index],
            bootstrap_values[upper_index],
        ],
        "matched_episodes": len(reference_rows),
        "base_scenario_groups": len(groups),
        "resamples": resamples,
        "seed": seed,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two frozen runs with matched scenarios and policies"
    )
    parser.add_argument("reference_run", type=Path)
    parser.add_argument("candidate_run", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    reference = load_run(args.reference_run)
    candidate = load_run(args.candidate_run)
    validate_compatibility(reference, candidate)
    reference_by_key = {episode_key(row): row for row in reference["episodes"]}
    candidate_by_key = {episode_key(row): row for row in candidate["episodes"]}
    output_directory = args.output_dir or args.candidate_run
    output_directory.mkdir(parents=True, exist_ok=True)

    by_policy = {}
    csv_rows = []
    bootstrap_results = []
    for policy in reference["by_policy"]:
        scenario_ids = [Path(path).stem for path in reference["scenarios"]]
        reference_rows = [
            reference_by_key[(scenario_id, policy)] for scenario_id in scenario_ids
        ]
        candidate_rows = [
            candidate_by_key[(scenario_id, policy)] for scenario_id in scenario_ids
        ]
        reference_summary = aggregate(reference_rows)
        candidate_summary = aggregate(candidate_rows)
        delta = {
            field: candidate_summary[field] - reference_summary[field]
            for field in reference_summary
            if field != "episodes"
        }
        by_policy[policy] = {
            "reference": reference_summary,
            "candidate": candidate_summary,
            "delta_candidate_minus_reference": delta,
            "outcome_transitions": outcome_transitions(
                reference_rows, candidate_rows
            ),
        }
        csv_rows.append(
            {
                "policy": policy,
                "episodes": len(reference_rows),
                **{
                    f"reference_{field}": value
                    for field, value in reference_summary.items()
                    if field != "episodes"
                },
                **{
                    f"candidate_{field}": value
                    for field, value in candidate_summary.items()
                    if field != "episodes"
                },
                **{f"delta_{field}": value for field, value in delta.items()},
            }
        )
        for metric in BOOTSTRAP_METRICS:
            bootstrap_results.append(
                budget_bootstrap(
                    reference_rows,
                    candidate_rows,
                    policy,
                    metric,
                    candidate["bootstrap_resamples"],
                    candidate["bootstrap_seed"],
                )
            )

    report = {
        "reference_run": str(args.reference_run),
        "candidate_run": str(args.candidate_run),
        "reference_config_id": reference["config_id"],
        "candidate_config_id": candidate["config_id"],
        "reference_verification_budget": reference["verification_budget"],
        "candidate_verification_budget": candidate["verification_budget"],
        "matched_scenarios": len(reference["scenarios"]),
        "matched_policy_episodes_per_budget": len(reference["episodes"]),
        "by_policy": by_policy,
        "paired_bootstrap": bootstrap_results,
        "interpretation": (
            "Independent model calls are aligned by scenario and policy, not by "
            "identical planner traces. Differences describe these two frozen runs; "
            "they do not isolate a causal budget effect or support broad generalization."
        ),
        "warning": (
            "Synthetic benchmark with clustered scenario variants. Bootstrap "
            "intervals resample base scenario groups and quantify run variability "
            "only within this benchmark."
        ),
    }
    json_path = output_directory / "budget_matched_comparison.json"
    csv_path = output_directory / "budget_matched_metrics.csv"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(csv_path, csv_rows)
    print(json.dumps(by_policy, indent=2, ensure_ascii=False))
    print(f"Saved matched budget comparison to {json_path}")
    print(f"Saved matched budget metrics to {csv_path}")


if __name__ == "__main__":
    main()
