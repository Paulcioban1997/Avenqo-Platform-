"""Stable tenant/user/conversation-scoped identities for AI requests."""

from uuid import NAMESPACE_URL, UUID, uuid4, uuid5


def resolve_ai_request_id(
    idempotency_key: str | None,
    *,
    tenant_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
) -> str:
    if idempotency_key is None or not idempotency_key.strip():
        return str(uuid4())
    key = idempotency_key.strip()
    if len(key) > 100:
        raise ValueError("Idempotency key is too long")
    return str(uuid5(
        NAMESPACE_URL,
        f"avenqo-ai:v1:{tenant_id}:{user_id}:{conversation_id}:{key}",
    ))


def reconcile_idempotency_keys(header_key: str | None, body_key: str | None) -> str | None:
    header = header_key.strip() if header_key else None
    body = body_key.strip() if body_key else None
    if header_key is not None and not header:
        raise ValueError("Idempotency-Key is invalid")
    if body_key is not None and not body:
        raise ValueError("Idempotency-Key is invalid")
    if header and body and header != body:
        raise ValueError("Idempotency-Key header and body value do not match")
    key = header or body
    if key is not None and (not key or len(key) > 100):
        raise ValueError("Idempotency-Key is invalid")
    return key