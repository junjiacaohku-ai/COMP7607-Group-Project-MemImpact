import argparse
import json
from pathlib import Path

from memimpact.core import CandidateAction
from memimpact.toolsandbox_adapter import execute_fixture_action


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute one action in ToolSandbox")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.request.read_text(encoding="utf-8"))
    action = CandidateAction(**payload["action"])
    result = execute_fixture_action(action, payload["fixture"])
    args.response.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
