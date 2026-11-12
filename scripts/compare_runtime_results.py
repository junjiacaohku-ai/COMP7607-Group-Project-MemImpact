import argparse
import json
from pathlib import Path
from typing import Any

SEMANTIC_FIELDS = (
    "paired_samples",
    "verification_budget",
    "initial_action",
    "baseline_flip_rate",
    "comparisons",
    "selected_memory_ids",
    "verification_results",
    "decision",
    "final_action",
    "task_success",
    "harmful_execution",
    "abstained",
    "planner_calls",
    "memory_verification_calls",
    "lookup_calls",
    "verification_calls",
    "tool_calls",
)


def episode_key(row: dict[str, Any]) -> tuple[str, str]:
    return row["scenario_id"], row["policy"]


def execution_semantics(row: dict[str, Any]) -> dict[str, Any]:
    execution = row.get("execution") or {}
    return {
        "executed": execution.get("executed", False),
        "deleted_reminder_ids": execution.get("deleted_reminder_ids"),
        "messages": [
            {
                "recipient_phone_number": message.get("recipient_phone_number"),
                "content": message.get("content"),
            }
            for message in execution.get("final_messages", [])
        ],
        "reminders": [
            {
                "content": reminder.get("content"),
                "reminder_timestamp": reminder.get("reminder_timestamp"),
            }
            for reminder in execution.get("final_reminders", [])
        ],
    }


def semantic_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **{field: row.get(field) for field in SEMANTIC_FIELDS},
        "execution": execution_semantics(row),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare decision and outcome semantics between two runtime runs"
    )
    parser.add_argument("reference_run", type=Path)
    parser.add_argument("candidate_run", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    reference_path = args.reference_run / "comparison_summary.json"
    candidate_path = args.candidate_run / "comparison_summary.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    reference_rows = {episode_key(row): row for row in reference["episodes"]}
    candidate_rows = {episode_key(row): row for row in candidate["episodes"]}
    shared_keys = sorted(reference_rows.keys() & candidate_rows.keys())
    missing = {
        "reference_only": [list(key) for key in sorted(reference_rows.keys() - candidate_rows.keys())],
        "candidate_only": [list(key) for key in sorted(candidate_rows.keys() - reference_rows.keys())],
    }

    differences = []
    for scenario_id, policy in shared_keys:
        reference_projection = semantic_projection(reference_rows[(scenario_id, policy)])
        candidate_projection = semantic_projection(candidate_rows[(scenario_id, policy)])
        fields = {
            field: {"reference": reference_projection[field], "candidate": candidate_projection[field]}
            for field in reference_projection
            if reference_projection[field] != candidate_projection[field]
        }
        if fields:
            differences.append(
                {"scenario_id": scenario_id, "policy": policy, "fields": fields}
            )

    report = {
        "reference_run": str(args.reference_run),
        "candidate_run": str(args.candidate_run),
        "matched_episodes": len(shared_keys),
        "semantically_equal_episodes": len(shared_keys) - len(differences),
        "equivalent": not differences and not missing["reference_only"] and not missing["candidate_only"],
        "missing": missing,
        "differences": differences,
        "cost_fields_excluded": [
            "planner_attempts",
            "planner_latency_ms",
            "planner_token_usage",
        ],
        "interpretation": (
            "Strict equality is intended for matched deterministic planner inputs. "
            "Independent model calls can legitimately produce different decisions."
        ),
    }
    output = args.output or args.candidate_run / "runtime_semantics.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "differences"}, indent=2))
    print(f"Saved runtime semantics comparison to {output}")
    if args.strict and not report["equivalent"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
