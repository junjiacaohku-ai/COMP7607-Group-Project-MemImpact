import json
from pathlib import Path

from tool_sandbox.common.tool_conversion import convert_to_openai_tools

from memimpact.planner import TOOL_REGISTRY

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    tools = convert_to_openai_tools(TOOL_REGISTRY)
    output = {
        tool["function"]["name"]: tool
        for tool in tools
    }
    path = PROJECT_ROOT / "configs" / "toolsandbox_tools.json"
    path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(output)} tool schemas to {path}")


if __name__ == "__main__":
    main()
