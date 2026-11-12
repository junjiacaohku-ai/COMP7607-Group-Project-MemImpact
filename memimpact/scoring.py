from datetime import datetime

from memimpact.core import MemoryRecord


def observable_uncertainty(memory: MemoryRecord, current_time: str) -> float:
    current = datetime.fromisoformat(current_time)
    remembered = datetime.fromisoformat(memory.timestamp)
    age_days = max(0.0, (current - remembered).total_seconds() / 86400)
    age_factor = 1.0 + min(age_days / 365.0, 1.0)
    provenance_factor = 1.0 if memory.provenance else 1.25
    return age_factor * provenance_factor


def verification_score(
    memory: MemoryRecord,
    impact: float,
    current_time: str,
    consequence: float = 1.0,
    verifier_cost: float = 1.0,
) -> float:
    if verifier_cost <= 0:
        raise ValueError("verifier_cost must be positive")
    return (
        consequence
        * observable_uncertainty(memory, current_time)
        * impact
        / verifier_cost
    )
