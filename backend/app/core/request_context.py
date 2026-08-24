"""Contexte de requête partagé via `contextvars` (Phase 34).

Permet de propager `request_id` dans TOUS les logs (y compris AI Gateway,
Tool Calling, Prediction) sans modifier chaque signature de fonction —
résout la limitation documentée en Phase 32 (voir
docs/ai-support-and-provider-resilience.md).
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()
