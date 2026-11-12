import random
from collections import defaultdict
from typing import Any


def metric_value(row: dict[str, Any], metric: str) -> float:
    if metric == "total_tokens":
        return float(row["planner_token_usage"]["total_tokens"])
    return float(row[metric])


def paired_bootstrap(
    episodes: list[dict[str, Any]],
    left_policy: str,
    right_policy: str,
    metric: str,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    left = {
        row["scenario_id"]: row
        for row in episodes
        if row["policy"] == left_policy
    }
    right = {
        row["scenario_id"]: row
        for row in episodes
        if row["policy"] == right_policy
    }
    matched_ids = sorted(set(left) & set(right))
    if not matched_ids:
        raise ValueError(f"No matched episodes for {left_policy} and {right_policy}")

    grouped = defaultdict(list)
    for scenario_id in matched_ids:
        base_id = left[scenario_id].get("base_scenario_id", scenario_id)
        difference = metric_value(left[scenario_id], metric) - metric_value(
            right[scenario_id], metric
        )
        grouped[base_id].append(difference)
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
        "left_policy": left_policy,
        "right_policy": right_policy,
        "metric": metric,
        "effect_definition": f"{left_policy} minus {right_policy}",
        "observed_difference": observed,
        "ci_95": [
            bootstrap_values[lower_index],
            bootstrap_values[upper_index],
        ],
        "matched_episodes": len(matched_ids),
        "base_scenario_groups": len(groups),
        "resamples": resamples,
        "seed": seed,
    }
