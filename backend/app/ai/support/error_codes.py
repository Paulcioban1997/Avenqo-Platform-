"""Codes d'erreur métier sûrs, réutilisables par le Support AI (Phase 32).

Chaque code est associé à une explication en langage clair — jamais un
détail technique/interne (stack trace, nom de fournisseur, etc.).
"""

from __future__ import annotations

SAFE_ERROR_EXPLANATIONS: dict[str, str] = {
    "DATA_IMPORT_FAILED": "Avenqo couldn't import this file. This usually means a required column is missing or the file format isn't recognized.",
    "MODEL_NOT_AVAILABLE": "This prediction isn't available yet. The underlying model may need more historical data or hasn't finished training.",
    "AI_QUOTA_REACHED": "Your company has reached its AI usage limit for this billing period. An account owner can review usage under Billing.",
    "PROVIDER_TEMPORARILY_UNAVAILABLE": "Avenqo AI is temporarily unavailable. This isn't a data problem — please try again shortly.",
    "CONNECTION_REQUIRED": "This feature needs at least one connected data source. Go to Connections to add one.",
}


def explain_error_code(code: str) -> str | None:
    return SAFE_ERROR_EXPLANATIONS.get(code.upper())
