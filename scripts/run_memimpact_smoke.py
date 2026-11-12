import argparse
import datetime
import json
from pathlib import Path

from memimpact.episode import run_episode
from memimpact.planner import TOOL_REGISTRY, CandidatePlanner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one paired memory audit, verification, replan, and execution"
    )
    parser.add_argument(
        "--scenario", type=Path, default=PROJECT_ROOT / "scenarios" / "pilot" / "stale_phone.json"
    )
    parser.add_argument("--model", default="qwen3.8-flash")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--verification-budget", type=int, default=1)
    parser.add_argument("--max-planner-attempts", type=int, default=2)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "results" / "memimpact_smoke"
    )
    args = parser.parse_args()
    if args.samples < 1:
        raise ValueError("--samples must be at least 1")

    fixture = json.loads(args.scenario.read_text(encoding="utf-8"))
    unknown_tools = set(fixture["available_tools"]) - set(TOOL_REGISTRY)
    if unknown_tools:
        raise ValueError(f"Unknown tools: {sorted(unknown_tools)}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_directory = args.output_dir / f"{fixture['scenario_id']}_{timestamp}"
    output_directory.mkdir(parents=True, exist_ok=True)
    planner = CandidatePlanner(
        args.model,
        args.temperature,
        thinking=not args.disable_thinking,
        max_attempts=args.max_planner_attempts,
    )
    result, traces = run_episode(
        fixture,
        "memimpact",
        planner,
        args.samples,
        output_directory,
        args.verification_budget,
    )
    (output_directory / "result_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_directory / "trace.json").write_text(
        json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Saved results to {output_directory}")


if __name__ == "__main__":
    main()
