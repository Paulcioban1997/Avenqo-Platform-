"""Safety policy for tenant CRM notification recipients."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID


_TEST_MARKERS = frozenset({"test", "testing", "demo", "seed", "fake", "fixture", "sample", "dummy"})
_RESERVED_DOMAINS = frozenset({
    "example.com",
    "example.net",
    "example.org",
    "avenqo-audit.ca",
    "avenqo-e2e.ca",
    "production-test.ca",
})


@dataclass(frozen=True, slots=True)
class RecipientDecision:
    allowed: bool
    status: str
    reason: str


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(value or "").strip().casefold())
        if token
    }


def is_test_email(value: str | None) -> bool:
    normalized = str(value or "").strip().casefold()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        return True
    local_part, domain = normalized.rsplit("@", 1)
    if domain in _RESERVED_DOMAINS or domain.endswith((".test", ".invalid", ".example")):
        return True
    if domain.endswith(tuple(f".{item}" for item in _RESERVED_DOMAINS)):
        return True
    return bool(_tokens(local_part) & _TEST_MARKERS) or normalized == "crm_test_client@avenqo.ca"


def is_test_phone(value: str | None) -> bool:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if not 8 <= len(digits) <= 15 or len(set(digits)) == 1:
        return True
    nanp = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
    if len(nanp) == 10 and nanp[3:6] == "555" and 100 <= int(nanp[6:]) <= 199:
        return True
    return False


def is_test_contact(client: Any) -> bool:
    identity_values = (
        getattr(client, "first_name", ""),
        getattr(client, "last_name", ""),
        getattr(client, "company_name", ""),
    )
    tags = getattr(client, "tags", None) or []
    return any(_tokens(value) & _TEST_MARKERS for value in (*identity_values, *tags))


def evaluate_crm_recipient(client: Any, company_id: UUID, channel: str) -> RecipientDecision:
    if getattr(client, "company_id", None) != company_id or bool(getattr(client, "is_deleted", False)):
        return RecipientDecision(False, "blocked_invalid_recipient", "tenant_or_deleted_contact")
    if str(getattr(client, "status", "")).casefold() == "archived":
        return RecipientDecision(False, "blocked_invalid_recipient", "archived_contact")
    if is_test_contact(client):
        return RecipientDecision(False, "blocked_test_recipient", "test_contact_identity")
    if channel == "email" and is_test_email(getattr(client, "email", None)):
        return RecipientDecision(False, "blocked_test_recipient", "test_or_invalid_email")
    if channel == "sms" and is_test_phone(getattr(client, "phone", None)):
        return RecipientDecision(False, "blocked_test_recipient", "test_or_invalid_phone")
    return RecipientDecision(True, "queued", "validated_tenant_contact")
