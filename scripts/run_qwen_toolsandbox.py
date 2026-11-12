import argparse
import datetime
import json
import subprocess
from importlib.metadata import version
from pathlib import Path

from tool_sandbox.cli.utils import resolve_scenarios
from tool_sandbox.common.execution_context import RoleType
from tool_sandbox.common.tool_discovery import ToolBackend
from tool_sandbox.roles.execution_environment import ExecutionEnvironment
from tool_sandbox.roles.openai_api_agent import OpenAIAPIAgent
from tool_sandbox.roles.openai_api_user import OpenAIAPIUser

from memimpact.qwen import make_qwen_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLSANDBOX_ROOT = PROJECT_ROOT / "third_party" / "ToolSandbox"


class QwenAgent(OpenAIAPIAgent):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.openai_client = make_qwen_client()


class QwenUser(OpenAIAPIUser):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.openai_client = make_qwen_client()


def toolsandbox_revision() -> str:
    return subprocess.check_output(
        ["git", "-C", str(TOOLSANDBOX_ROOT), "rev-parse", "HEAD"], text=True
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one ToolSandbox scenario with Qwen via DashScope"
    )
    parser.add_argument("--scenario", default="wifi_off")
    parser.add_argument("--model", default="qwen3.8-flash")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "toolsandbox_smoke",
    )
    args = parser.parse_args()

    scenarios = resolve_scenarios(
        desired_scenario_names=[args.scenario],
        preferred_tool_backend=ToolBackend.DEFAULT,
    )
    scenario = scenarios[args.scenario]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_directory = args.output_dir / f"{args.model}_{args.scenario}_{timestamp}"

    roles = {
        RoleType.USER: QwenUser(args.model),
        RoleType.EXECUTION_ENVIRONMENT: ExecutionEnvironment(),
        RoleType.AGENT: QwenAgent(args.model),
    }
    try:
        result = scenario.play_and_evaluate(
            roles=roles,
            output_directory=output_directory,
            scenario_name=args.scenario,
        )
        evaluation = result.evaluation_result
        summary = {
            "name": args.scenario,
            "model": args.model,
            "similarity": evaluation.similarity,
            "milestone_similarity": evaluation.milestone_similarity,
            "minefield_similarity": evaluation.minefield_similarity,
            "turn_count": evaluation.turn_count,
            "milestone_mapping": evaluation.milestone_mapping,
            "minefield_mapping": evaluation.minefield_mapping,
            "toolsandbox_git_sha": toolsandbox_revision(),
            "openai_package_version": version("openai"),
            "httpx_package_version": version("httpx"),
        }
        output_directory.mkdir(parents=True, exist_ok=True)
        (output_directory / "result_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"Saved results to {output_directory}")
    finally:
        for role in roles.values():
            role.teardown()


if __name__ == "__main__":
    main()
