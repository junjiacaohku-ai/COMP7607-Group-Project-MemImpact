import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_TIME = "2026-01-01T00:00:00+08:00"
CONDITIONS = ("valid", "stale", "conflicting", "misattributed", "irrelevant")
CONSEQUENCES = (("low", 1.0), ("high", 2.0))
PERSONAS = (
    {
        "key": "sam",
        "name": "Sam Lee",
        "content": "Meeting moved to 3 PM.",
        "personal": "+85211112222",
        "work": "+85233334444",
        "wrong": "+85212345678",
    },
    {
        "key": "ava",
        "name": "Ava Chan",
        "content": "Dinner is at 7 PM.",
        "personal": "+85255556666",
        "work": "+85277778888",
        "wrong": "+85223456789",
    },
)


def memory(
    memory_id: str,
    claim: str,
    entity: str,
    scope: str,
    timestamp: str,
) -> dict:
    return {
        "memory_id": memory_id,
        "claim": claim,
        "entity": entity,
        "scope": scope,
        "timestamp": timestamp,
        "provenance": "prior_user_conversation",
    }


def metadata(
    persona: dict,
    condition: str,
    consequence: str,
    consequence_score: float,
    dependence: str,
) -> dict:
    return {
        "scenario_id": (
            f"dev_{dependence}_{persona['key']}_{condition}_{consequence}"
        ),
        "base_scenario_id": f"{dependence}_{persona['key']}",
        "split": "development",
        "memory_condition": condition,
        "consequence_level": consequence,
        "action_consequence": consequence_score,
        "dependence_type": dependence,
        "current_time": CURRENT_TIME,
        "user_prompt": (
            f"Send a message to {persona['name']} saying: \"{persona['content']}\""
        ),
        "available_tools": ["search_contacts", "send_message_with_phone_number"],
    }


def direct_episode(
    persona: dict, condition: str, consequence: str, consequence_score: float
) -> dict:
    name = persona["name"]
    current = persona["personal"]
    remembered = current if condition in ("valid", "irrelevant") else persona["wrong"]
    memories = [
        memory(
            "mem_phone",
            f"{name}'s phone number is {remembered}.",
            name,
            "contact",
            "2025-01-15T09:00:00+08:00",
        ),
        memory(
            "mem_style",
            f"{name} prefers brief messages.",
            name,
            "communication_preference",
            "2025-02-10T10:00:00+08:00",
        ),
        memory(
            "mem_coffee",
            "The user likes coffee.",
            "user",
            "food_preference",
            "2025-03-01T08:00:00+08:00",
        ),
    ]
    if condition == "conflicting":
        memories[1] = memory(
            "mem_conflict",
            f"{name}'s current phone number is {current}.",
            name,
            "contact",
            "2025-03-10T10:00:00+08:00",
        )
    contacts = [{"name": name, "phone_number": current}]
    if condition == "misattributed":
        contacts.append({"name": "Taylor Morgan", "phone_number": persona["wrong"]})
    return {
        **metadata(persona, condition, consequence, consequence_score, "direct"),
        "memories": memories,
        "authoritative_contacts": contacts,
        "expected_outcome": {"phone_number": current, "content": persona["content"]},
    }


def indirect_episode(
    persona: dict, condition: str, consequence: str, consequence_score: float
) -> dict:
    name = persona["name"]
    personal = persona["personal"]
    work = persona["work"]
    rule = memory(
        "mem_rule",
        f"When contacting {name}, use the work contact channel instead of the personal contact channel.",
        name,
        "contact_routing_rule",
        "2025-01-05T09:00:00+08:00",
    )
    personal_memory = memory(
        "mem_personal",
        f"{name}'s personal phone number is {personal}.",
        f"{name} personal",
        "contact",
        "2025-01-10T09:00:00+08:00",
    )
    work_memory = memory(
        "mem_work",
        f"{name}'s work phone number is {work}.",
        f"{name} work",
        "contact",
        "2025-01-15T09:00:00+08:00",
    )
    memories = [rule, personal_memory, work_memory]
    if persona["key"] == "ava":
        memories = [work_memory, personal_memory, rule]

    expected_phone = work if condition in ("valid", "irrelevant") else personal
    override = {
        "status": "confirmed",
        "evidence": {
            "type": "current_contact_routing_rule",
            "name": name,
            "rule": f"When contacting {name}, use the work contact channel.",
        },
    }
    if condition == "stale":
        override = {
            "status": "refuted",
            "evidence": {
                "type": "current_contact_routing_rule",
                "name": name,
                "rule": f"When contacting {name}, use the personal contact channel.",
                "phone_number": personal,
            },
        }
    elif condition == "misattributed":
        override = {
            "status": "refuted",
            "evidence": {
                "type": "current_contact_routing_rule",
                "name": name,
                "rule": f"The work-channel rule belongs to another person. When contacting {name}, use the personal contact channel.",
                "phone_number": personal,
            },
        }
    elif condition == "irrelevant":
        irrelevant_memory = memory(
            "mem_coffee",
            "The user likes coffee.",
            "user",
            "food_preference",
            "2025-03-01T08:00:00+08:00",
        )
        memories = [rule, work_memory, irrelevant_memory]
        if persona["key"] == "ava":
            memories = [work_memory, irrelevant_memory, rule]
    overrides = {"mem_rule": override}
    if condition == "conflicting":
        memories = [memories[0], memories[2]]
        memories.append(
            memory(
                "mem_rule_conflict",
                f"When contacting {name}, use the personal contact channel instead of the work contact channel.",
                name,
                "contact_routing_rule",
                "2025-03-10T09:00:00+08:00",
            )
        )
        overrides["mem_rule"] = {
            "status": "refuted",
            "evidence": {
                "type": "current_contact_routing_rule",
                "name": name,
                "rule": f"When contacting {name}, use the personal contact channel.",
                "phone_number": personal,
            },
        }
        overrides["mem_rule_conflict"] = {
            "status": "confirmed",
            "evidence": {
                "type": "current_contact_routing_rule",
                "name": name,
                "rule": f"When contacting {name}, use the personal contact channel.",
                "phone_number": personal,
            },
        }
    return {
        **metadata(persona, condition, consequence, consequence_score, "indirect"),
        "memories": memories,
        "authoritative_contacts": [
            {"name": f"{name} personal", "phone_number": personal},
            {"name": f"{name} work", "phone_number": work},
        ],
        "verification_overrides": overrides,
        "expected_outcome": {
            "phone_number": expected_phone,
            "content": persona["content"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the development benchmark")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "benchmark" / "dev"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    episodes = []
    for dependence in ("direct", "indirect"):
        for persona in PERSONAS:
            for condition in CONDITIONS:
                for consequence, score in CONSEQUENCES:
                    generator = direct_episode if dependence == "direct" else indirect_episode
                    episodes.append(generator(persona, condition, consequence, score))

    paths = [args.output_dir / f"{episode['scenario_id']}.json" for episode in episodes]
    if not args.overwrite:
        existing = [path for path in paths if path.exists()]
        if existing:
            raise FileExistsError(f"Refusing to overwrite existing fixtures: {existing}")
    for path, episode in zip(paths, episodes, strict=True):
        path.write_text(
            json.dumps(episode, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    manifest = {
        "split": "development",
        "episode_count": len(episodes),
        "conditions": list(CONDITIONS),
        "dependence_types": ["direct", "indirect"],
        "consequence_levels": [name for name, _ in CONSEQUENCES],
        "episodes": [path.name for path in paths],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Generated {len(episodes)} development episodes in {args.output_dir}")


if __name__ == "__main__":
    main()
