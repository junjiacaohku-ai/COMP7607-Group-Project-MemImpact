import json
import subprocess
import tempfile
from pathlib import Path

from memimpact.core import CandidateAction

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ToolSandboxProcessExecutor:
    def __init__(self) -> None:
        self.python = PROJECT_ROOT / ".venv-toolsandbox" / "bin" / "python"
        self.worker = PROJECT_ROOT / "scripts" / "toolsandbox_worker.py"

    def __call__(self, action: CandidateAction, fixture: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            response = Path(directory) / "response.json"
            request.write_text(
                json.dumps(
                    {"action": action.model_dump(), "fixture": fixture},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    str(self.python),
                    str(self.worker),
                    "--request",
                    str(request),
                    "--response",
                    str(response),
                ],
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()
                raise RuntimeError(
                    f"ToolSandbox worker failed with exit {completed.returncode}"
                    + (f":\n{detail}" if detail else "")
                )
            return json.loads(response.read_text(encoding="utf-8"))
