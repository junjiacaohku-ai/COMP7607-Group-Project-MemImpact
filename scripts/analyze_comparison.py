import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from memimpact.statistics import paired_bootstrap

POLICY_LABELS = {
    "memimpact": "MemImpact",
    "memimpact_flip": "Flip-only",
    "always_proceed": "Always proceed",
    "always_verify": "Always verify",
    "static": "Static",
    "amv_guard": "AMV-style",
}
POLICY_COLORS = {
    "memimpact": "#0072B2",
    "memimpact_flip": "#56B4E9",
    "always_proceed": "#D55E00",
    "always_verify": "#009E73",
    "static": "#CC79A7",
    "amv_guard": "#E69F00",
}
def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("No rows to write")
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def lookup_calls(row: dict) -> int:
    if "lookup_calls" in row:
        return row["lookup_calls"]
    if row.get("lookup_execution") is not None:
        return 1
    execution = row.get("execution") or {}
    return int(execution.get("lookup") is not None)


def memory_verification_calls(row: dict) -> int:
    return row.get("memory_verification_calls", row["verification_calls"])


def total_verification_calls(row: dict) -> int:
    if "memory_verification_calls" in row:
        return row["verification_calls"]
    return memory_verification_calls(row) + lookup_calls(row)


def critical_memory_metrics(run_directory: Path, episodes: list[dict]) -> dict:
    counts = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    labeled_episodes = 0
    for row in episodes:
        label_path = run_directory / row["scenario_id"] / "critical_labels.json"
        if not label_path.exists():
            continue
        labels = json.loads(label_path.read_text(encoding="utf-8"))
        expected = set(labels["critical_memory_ids"])
        predicted = set(row["selected_memory_ids"])
        counts[row["policy"]]["tp"] += len(predicted & expected)
        counts[row["policy"]]["fp"] += len(predicted - expected)
        counts[row["policy"]]["fn"] += len(expected - predicted)
        labeled_episodes += 1
    metrics = {}
    for policy, count in counts.items():
        precision_denominator = count["tp"] + count["fp"]
        recall_denominator = count["tp"] + count["fn"]
        metrics[policy] = {
            **count,
            "precision": (
                count["tp"] / precision_denominator
                if precision_denominator
                else None
            ),
            "recall": (
                count["tp"] / recall_denominator if recall_denominator else None
            ),
        }
    return {"labeled_policy_episodes": labeled_episodes, "by_policy": metrics}


def grouped_metrics(episodes: list[dict], group_field: str) -> list[dict]:
    groups = sorted({(row.get(group_field, "unlabeled"), row["policy"]) for row in episodes})
    rows = []
    for group_value, policy in groups:
        selected = [
            row
            for row in episodes
            if row.get(group_field, "unlabeled") == group_value and row["policy"] == policy
        ]
        rows.append(
            {
                "group_field": group_field,
                "group_value": group_value,
                "policy": policy,
                "episodes": len(selected),
                "task_success_rate": sum(row["task_success"] for row in selected)
                / len(selected),
                "harmful_execution_rate": sum(
                    row["harmful_execution"] for row in selected
                )
                / len(selected),
                "abstention_rate": sum(row["abstained"] for row in selected)
                / len(selected),
                "mean_verification_calls": sum(
                    total_verification_calls(row) for row in selected
                )
                / len(selected),
                "mean_total_tokens": sum(
                    row["planner_token_usage"]["total_tokens"] for row in selected
                )
                / len(selected),
                "mean_planner_latency_ms": sum(
                    row["planner_latency_ms"] for row in selected
                )
                / len(selected),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create tables and reliability-cost plots from a comparison run"
    )
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    data = json.loads(args.comparison.read_text(encoding="utf-8"))
    output_directory = args.output_dir or args.comparison.parent
    output_directory.mkdir(parents=True, exist_ok=True)
    policies = list(data["by_policy"])
    policy_summaries = {}
    metrics = []
    for policy in policies:
        policy_rows = [
            row for row in data["episodes"] if row["policy"] == policy
        ]
        summary = dict(data.get("by_policy", {})[policy])
        summary["memory_verification_calls"] = sum(
            memory_verification_calls(row) for row in policy_rows
        )
        summary["lookup_calls"] = sum(lookup_calls(row) for row in policy_rows)
        summary["verification_calls"] = sum(
            total_verification_calls(row) for row in policy_rows
        )
        policy_summaries[policy] = summary
        metrics.append({"policy": policy, **summary})
    write_csv(output_directory / "policy_metrics.csv", metrics)

    episode_rows = []
    for row in data["episodes"]:
        episode_rows.append(
            {
                "scenario_id": row["scenario_id"],
                "base_scenario_id": row.get("base_scenario_id", row["scenario_id"]),
                "memory_condition": row.get("memory_condition", "unlabeled"),
                "consequence_level": row.get("consequence_level", "unlabeled"),
                "dependence_type": row.get("dependence_type", "unlabeled"),
                "policy": row["policy"],
                "task_success": row["task_success"],
                "harmful_execution": row["harmful_execution"],
                "abstained": row["abstained"],
                "memory_verification_calls": memory_verification_calls(row),
                "lookup_calls": lookup_calls(row),
                "verification_calls": total_verification_calls(row),
                "planner_calls": row["planner_calls"],
                "planner_attempts": row["planner_attempts"],
                "total_tokens": row["planner_token_usage"]["total_tokens"],
                "planner_latency_ms": row["planner_latency_ms"],
                "selected_memory_ids": ";".join(row["selected_memory_ids"]),
            }
        )
    write_csv(output_directory / "per_episode_metrics.csv", episode_rows)
    grouped_rows = []
    for group_field in ("memory_condition", "consequence_level", "dependence_type"):
        grouped_rows.extend(grouped_metrics(data["episodes"], group_field))
    write_csv(output_directory / "grouped_metrics.csv", grouped_rows)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    x = range(len(policies))
    axes[0].bar(
        [index - 0.18 for index in x],
        [policy_summaries[policy]["task_success_rate"] for policy in policies],
        width=0.36,
        label="Task success",
        color=[POLICY_COLORS[policy] for policy in policies],
    )
    axes[0].bar(
        [index + 0.18 for index in x],
        [policy_summaries[policy]["harmful_execution_rate"] for policy in policies],
        width=0.36,
        label="Harmful execution",
        color="#D55E00",
        alpha=0.65,
        hatch="//",
    )
    axes[0].set_xticks(list(x), [POLICY_LABELS[p] for p in policies], rotation=25)
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("Rate")
    axes[0].set_title("Reliability and safety")
    axes[0].legend(frameon=False)

    for policy in policies:
        summary = policy_summaries[policy]
        axes[1].scatter(
            summary["total_tokens"],
            summary["task_success_rate"],
            color=POLICY_COLORS[policy],
            s=70,
            zorder=3,
        )
        axes[2].scatter(
            summary["verification_calls"],
            summary["task_success_rate"],
            color=POLICY_COLORS[policy],
            s=70,
            zorder=3,
        )
    axes[1].set_title("Reliability vs. planning cost")
    axes[1].set_xlabel("Total planner tokens")
    axes[1].set_ylabel("Task success rate")
    axes[1].set_ylim(-0.05, 1.1)
    axes[1].grid(alpha=0.2)
    axes[2].set_title("Reliability vs. verification cost")
    axes[2].set_xlabel("Verification calls")
    axes[2].set_ylabel("Task success rate")
    axes[2].set_ylim(-0.05, 1.1)
    axes[2].grid(alpha=0.2)
    fig.suptitle(
        f"MemImpact pilot | {data['model']} | {len(data['episodes'])} policy episodes"
    )
    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=POLICY_COLORS[policy],
            markersize=8,
            label=POLICY_LABELS[policy],
        )
        for policy in policies
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(policies),
        frameon=False,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(output_directory / "reliability_cost.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    critical_metrics = critical_memory_metrics(
        args.comparison.parent, data["episodes"]
    )
    (output_directory / "critical_memory_metrics.json").write_text(
        json.dumps(critical_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    bootstrap_results = []
    if "memimpact" in policies:
        for other in ("amv_guard", "static", "always_verify", "always_proceed"):
            if other not in policies:
                continue
            for metric in ("task_success", "harmful_execution", "total_tokens"):
                bootstrap_results.append(
                    paired_bootstrap(
                        data["episodes"],
                        "memimpact",
                        other,
                        metric,
                        data.get("bootstrap_resamples", 2000),
                        data.get("bootstrap_seed", 42),
                    )
                )
    (output_directory / "paired_bootstrap.json").write_text(
        json.dumps(bootstrap_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    analysis = {
        "source": str(args.comparison),
        "model": data["model"],
        "paired_samples": data["paired_samples"],
        "cost_semantics": data.get("cost_semantics"),
        "policy_metrics": policy_summaries,
        "critical_memory_metrics_file": "critical_memory_metrics.json",
        "paired_bootstrap_file": "paired_bootstrap.json",
        "warning": "Small synthetic pilot; no statistical generalization is claimed.",
    }
    (output_directory / "analysis_summary.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Saved analysis to {output_directory}")


if __name__ == "__main__":
    main()
