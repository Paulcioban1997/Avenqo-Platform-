"""Classe les décisions par priorité — l'utilisateur ne voit jamais N alertes équivalentes."""

from __future__ import annotations

from typing import Sequence

from shared.ai_engine.decision_intelligence.contracts import BusinessDecision, Severity

_PRIORITY_ORDER = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFORMATIONAL,
)


def rank_decisions(decisions: Sequence[BusinessDecision]) -> tuple[BusinessDecision, ...]:
    """Trie par priorité (critique d'abord), puis par confiance décroissante."""

    return tuple(
        sorted(
            decisions,
            key=lambda decision: (
                _PRIORITY_ORDER.index(decision.priority),
                -decision.insight.confidence,
            ),
        )
    )
