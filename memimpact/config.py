from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from memimpact.episode import POLICIES


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    config_id: str
    description: str
    status: Literal["development", "validation_pilot", "heldout"]
    frozen: bool
    model: str
    temperature: float
    samples: int = Field(ge=1)
    thinking: bool
    verification_budget: int = Field(ge=0)
    max_planner_attempts: int = Field(ge=1)
    policies: list[str]
    scenarios: list[str]
    output_dir: str = "results/policy_comparison"
    bootstrap_resamples: int = Field(ge=1, default=2000)
    bootstrap_seed: int = 42
    toolsandbox_git_sha: str

    @field_validator("policies")
    @classmethod
    def validate_policies(cls, policies: list[str]) -> list[str]:
        unknown = set(policies) - set(POLICIES)
        if unknown:
            raise ValueError(f"Unknown policies: {sorted(unknown)}")
        if not policies:
            raise ValueError("At least one policy is required")
        return policies

    def scenario_paths(self, project_root: Path) -> list[Path]:
        paths = [project_root / scenario for scenario in self.scenarios]
        missing = [path for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Missing scenarios: {missing}")
        return paths


def load_experiment_config(path: Path) -> ExperimentConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ExperimentConfig(**data)
