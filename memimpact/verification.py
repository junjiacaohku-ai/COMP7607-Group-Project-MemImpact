import re
from typing import Any

from memimpact.core import MemoryRecord, VerificationResult


class AuthoritativeContactVerifier:
    def __init__(
        self,
        contacts: list[dict[str, Any]],
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.contacts = {contact["name"]: contact for contact in contacts}
        self.overrides = overrides or {}

    def verify(self, memory: MemoryRecord) -> VerificationResult:
        if memory.memory_id in self.overrides:
            override = self.overrides[memory.memory_id]
            return VerificationResult(
                memory_id=memory.memory_id,
                status=override["status"],
                evidence=override["evidence"],
            )
        contact = self.contacts.get(memory.entity)
        if memory.scope != "contact" or contact is None:
            return VerificationResult(
                memory_id=memory.memory_id,
                status="unknown",
                evidence=None,
            )

        match = re.search(r"\+\d+", memory.claim)
        remembered_phone = match.group(0) if match else None
        evidence = {
            "type": "authoritative_contact_record",
            "name": contact["name"],
            "phone_number": contact["phone_number"],
        }
        status = (
            "confirmed"
            if remembered_phone == contact["phone_number"]
            else "refuted"
        )
        return VerificationResult(
            memory_id=memory.memory_id,
            status=status,
            evidence=evidence,
        )
