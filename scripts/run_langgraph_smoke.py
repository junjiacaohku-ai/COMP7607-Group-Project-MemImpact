import argparse
import datetime
import json
from pathlib import Path

from memimpact.langgraph_runtime import run_langgraph_episode
from memimpact.policies import POLICIES
from memimpact.process_adapter import ToolSandboxProcessExecutor
from memimpact.providers import (
    PROVIDER_NAMES,
    create_provider,
    resolve_model,
    resolve_provider,
)
from memimpact.schema_planner import SchemaCandidatePlanner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one episode using LangGraph and the ToolSandbox worker"
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "deletion_pilot" / "stale_target.json",
    )
    parser.add_argument("--policy", choices=POLICIES, default="memimpact")
    parser.add_argument("--provider", choices=PROVIDER_NAMES, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--verification-budget", type=int, default=1)
    parser.add_argument("--max-planner-attempts", type=int, default=2)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "results" / "langgraph_smoke"
    )
    args = parser.parse_args()
    provider_name = resolve_provider(args.provider)
    model = resolve_model(provider_name, args.model)
    fixture = json.loads(args.scenario.read_text(encoding="utf-8"))
    planner = SchemaCandidatePlanner(
        model,
        args.temperature,
        thinking=not args.disable_thinking,
        max_attempts=args.max_planner_attempts,
        provider=create_provider(provider_name),
    )
    result, traces = run_langgraph_episode(
        fixture,
        args.policy,
        planner,
        args.samples,
        ToolSandboxProcessExecutor(),
        verification_budget=args.verification_budget,
    )
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_directory = args.output_dir / f"{fixture['scenario_id']}_{args.policy}_{timestamp}"
    output_directory.mkdir(parents=True, exist_ok=True)
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
