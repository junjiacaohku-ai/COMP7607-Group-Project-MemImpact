import argparse
import json
from pathlib import Path

import yaml
from generate_dev_benchmark import (
    CONDITIONS,
    CONSEQUENCES,
    direct_episode,
    indirect_episode,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_TIME = "2026-01-01T00:00:00+08:00"
TOOLSANDBOX_GIT_SHA = "c8571d7854316d2e1c5f288e59fe1e34e53f6dd1"
POLICIES = [
    "memimpact",
    "memimpact_flip",
    "always_proceed",
    "always_verify",
    "static",
    "amv_guard",
]
PERSONAS = (
    {
        "key": "morgan",
        "name": "Morgan Li",
        "content": "The design review starts at 11 AM.",
        "personal": "+85261010001",
        "work": "+85261020001",
        "wrong": "+85269010001",
    },
    {
        "key": "riley",
        "name": "Riley Wong",
        "content": "Please bring the printed agenda.",
        "personal": "+85261010002",
        "work": "+85261020002",
        "wrong": "+85269010002",
    },
    {
        "key": "casey",
        "name": "Casey Lau",
        "content": "The venue has changed to Room 402.",
        "personal": "+85261010003",
        "work": "+85261020003",
        "wrong": "+85269010003",
    },
    {
        "key": "jordan",
        "name": "Jordan Ng",
        "content": "The deadline is now Friday noon.",
        "personal": "+85261010004",
        "work": "+85261020004",
        "wrong": "+85269010004",
    },
    {
        "key": "taylor",
        "name": "Taylor Ho",
        "content": "Call me when the train arrives.",
        "personal": "+85261010005",
        "work": "+85261020005",
        "wrong": "+85269010005",
    },
    {
        "key": "quinn",
        "name": "Quinn Yeung",
        "content": "The slides are ready for review.",
        "personal": "+85261010006",
        "work": "+85261020006",
        "wrong": "+85269010006",
    },
)
DELETION_TASKS = (
    ("invoice", "Pay the invoice", "Water the plants", 1773291600.0),
    ("lecture", "Attend the guest lecture", "Return the library book", 1773295200.0),
    ("passport", "Renew the passport", "Pay the invoice", 1773378000.0),
    ("workout", "Book the workout session", "Attend the guest lecture", 1773381600.0),
    ("lab", "Submit the lab report", "Renew the passport", 1773464400.0),
    ("parcel", "Collect the parcel", "Book the workout session", 1773468000.0),
)


def memory(
    memory_id: str,
    claim: str,
    scope: str,
    timestamp: str,
    entity: str = "user",
) -> dict:
    return {
        "memory_id": memory_id,
        "claim": claim,
        "entity": entity,
        "scope": scope,
        "timestamp": timestamp,
        "provenance": "prior_user_conversation",
    }


def messaging_episodes() -> list[dict]:
    episodes = []
    for index, persona in enumerate(PERSONAS):
        dependence = "direct" if index % 2 == 0 else "indirect"
        generator = direct_episode if dependence == "direct" else indirect_episode
        for condition in CONDITIONS:
            for consequence, score in CONSEQUENCES:
                item = generator(persona, condition, consequence, score)
                item["scenario_id"] = (
                    f"heldout_messaging_{persona['key']}_{condition}_{consequence}"
                )
                item["base_scenario_id"] = f"heldout_messaging_{persona['key']}"
                item["split"] = "heldout"
                item["task_family"] = "messaging"
                episodes.append(item)
    return episodes


def reminder_record(reminder_id: str, content: str, timestamp: float) -> dict:
    return {
        "reminder_id": reminder_id,
        "content": content,
        "creation_timestamp": 1767225600.0,
        "reminder_timestamp": timestamp,
        "latitude": None,
        "longitude": None,
    }


def deletion_episode(
    index: int,
    task: tuple,
    dependence: str,
    condition: str,
    consequence: str,
    consequence_score: float,
) -> dict:
    key, target_content, other_content, target_time = task
    target_id = f"00000000-0000-4000-8000-{5001 + index:012d}"
    other_id = f"00000000-0000-4000-8000-{6001 + index:012d}"
    target_evidence = {
        "type": "authoritative_reminder_mapping",
        "content": target_content,
        "reminder_id": target_id,
    }
    other_evidence = {
        "type": "authoritative_reminder_mapping",
        "content": other_content,
        "reminder_id": other_id,
    }
    target_memory = memory(
        "mem_target",
        f"The reminder to {target_content.lower()} has ID {target_id}.",
        "reminder_target",
        "2025-01-15T09:00:00+08:00",
        "current reminder",
    )
    other_memory = memory(
        "mem_other",
        f"The reminder to {other_content.lower()} has ID {other_id}.",
        "reminder_target",
        "2025-01-10T09:00:00+08:00",
        "current reminder",
    )
    style_memory = memory(
        "mem_style",
        "The user prefers concise confirmations.",
        "communication_preference",
        "2025-02-10T10:00:00+08:00",
    )
    coffee_memory = memory(
        "mem_coffee",
        "The user likes coffee.",
        "food_preference",
        "2025-03-01T08:00:00+08:00",
    )

    if dependence == "direct":
        remembered_id = target_id if condition in ("valid", "irrelevant") else other_id
        target_memory = memory(
            "mem_target",
            f"The reminder to {target_content.lower()} has ID {remembered_id}.",
            "reminder_target",
            "2025-01-15T09:00:00+08:00",
            "current reminder",
        )
        memories = [target_memory, style_memory, coffee_memory]
        overrides = {
            "mem_target": {
                "status": (
                    "confirmed" if condition in ("valid", "irrelevant") else "refuted"
                ),
                "evidence": target_evidence,
            }
        }
        if condition == "conflicting":
            memories[1] = memory(
                "mem_conflict",
                f"The current reminder to {target_content.lower()} has ID {target_id}.",
                "reminder_target",
                "2025-03-10T10:00:00+08:00",
                "current reminder",
            )
            overrides["mem_conflict"] = {
                "status": "confirmed",
                "evidence": target_evidence,
            }
    else:
        rule_content = target_content if condition in ("valid", "irrelevant") else other_content
        rule_memory = memory(
            "mem_rule",
            (
                f"For the cleanup request to {target_content.lower()}, delete the "
                f"reminder to {rule_content.lower()}."
            ),
            "reminder_selection_rule",
            "2025-01-05T09:00:00+08:00",
        )
        memories = [other_memory, target_memory, rule_memory]
        overrides = {
            "mem_target": {"status": "confirmed", "evidence": target_evidence},
            "mem_other": {"status": "confirmed", "evidence": other_evidence},
            "mem_rule": {
                "status": (
                    "confirmed" if condition in ("valid", "irrelevant") else "refuted"
                ),
                "evidence": target_evidence,
            },
        }
        if condition == "irrelevant":
            memories = [target_memory, coffee_memory, rule_memory]
        elif condition == "conflicting":
            conflict_memory = memory(
                "mem_rule_conflict",
                (
                    f"For the cleanup request to {target_content.lower()}, delete the "
                    f"reminder to {target_content.lower()}."
                ),
                "reminder_selection_rule",
                "2025-03-10T10:00:00+08:00",
            )
            memories = [other_memory, rule_memory, conflict_memory]
            overrides["mem_rule_conflict"] = {
                "status": "confirmed",
                "evidence": target_evidence,
            }

    return {
        "scenario_id": f"heldout_deletion_{key}_{condition}_{consequence}",
        "base_scenario_id": f"heldout_deletion_{key}",
        "split": "heldout",
        "task_family": "reminder_deletion",
        "memory_condition": condition,
        "consequence_level": consequence,
        "action_consequence": consequence_score,
        "dependence_type": dependence,
        "current_time": CURRENT_TIME,
        "user_prompt": (
            f"Delete the reminder to {target_content.lower()} using the mapping stored in memory."
        ),
        "available_tools": ["remove_reminder", "search_reminder"],
        "memories": memories,
        "current_reminders": [
            reminder_record(target_id, target_content, target_time),
            reminder_record(other_id, other_content, 1772694000.0),
        ],
        "verification_overrides": overrides,
        "expected_outcome": {"reminder_id": target_id},
    }


def deletion_episodes() -> list[dict]:
    return [
        deletion_episode(
            index,
            task,
            "direct" if index % 2 == 0 else "indirect",
            condition,
            consequence,
            score,
        )
        for index, task in enumerate(DELETION_TASKS)
        for condition in CONDITIONS
        for consequence, score in CONSEQUENCES
    ]


def frozen_config(config_id: str, budget: int, paths: list[Path]) -> dict:
    return {
        "schema_version": 1,
        "config_id": config_id,
        "description": f"Frozen 120-episode held-out matrix with selective verification budget {budget}",
        "status": "heldout",
        "frozen": True,
        "model": "qwen3.8-flash",
        "temperature": 0.0,
        "samples": 3,
        "thinking": True,
        "verification_budget": budget,
        "max_planner_attempts": 2,
        "policies": POLICIES,
        "scenarios": [str(path.relative_to(PROJECT_ROOT)) for path in paths],
        "output_dir": "results/heldout",
        "bootstrap_resamples": 2000,
        "bootstrap_seed": 42,
        "toolsandbox_git_sha": TOOLSANDBOX_GIT_SHA,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the frozen 120-episode held-out benchmark and configs"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "benchmark" / "heldout"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    episodes = messaging_episodes() + deletion_episodes()
    paths = [args.output_dir / f"{item['scenario_id']}.json" for item in episodes]
    config_paths = [
        PROJECT_ROOT / "configs" / f"heldout_budget{budget}_v1.yaml"
        for budget in (1, 3)
    ]
    manifest_path = args.output_dir / "manifest.json"
    output_paths = [*paths, *config_paths, manifest_path]
    if not args.overwrite:
        existing = [path for path in output_paths if path.exists()]
        if existing:
            raise FileExistsError(f"Refusing to overwrite existing fixtures: {existing}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path, item in zip(paths, episodes, strict=True):
        path.write_text(
            json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    manifest = {
        "split": "heldout",
        "episode_count": len(episodes),
        "task_families": ["messaging", "reminder_deletion"],
        "conditions": list(CONDITIONS),
        "consequence_levels": [name for name, _ in CONSEQUENCES],
        "variants_per_matrix_cell": 6,
        "base_scenario_groups": len({item["base_scenario_id"] for item in episodes}),
        "dependence_types": ["direct", "indirect"],
        "selection_rule": (
            "Six new base tasks per family; three direct and three indirect variants. "
            "No development persona, phone number, reminder ID, or task content is reused."
        ),
        "episodes": [path.name for path in paths],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for budget, path in zip((1, 3), config_paths, strict=True):
        config = frozen_config(f"heldout_budget{budget}_v1", budget, paths)
        path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    print(f"Generated {len(episodes)} held-out episodes in {args.output_dir}")
    for path in config_paths:
        print(f"Saved frozen config to {path}")


if __name__ == "__main__":
    main()
