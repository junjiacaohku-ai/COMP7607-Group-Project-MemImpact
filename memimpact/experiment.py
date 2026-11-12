import subprocess
from pathlib import Path
from typing import Any


def summarize_policy(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
