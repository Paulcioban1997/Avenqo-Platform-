"""`DecisionEngine` — combine toutes les règles en une décision unique.

Point d'entrée algorithmique pur (aucun accès disque/registre ici — voir
`service.py` pour l'intégration défensive/never-raise utilisée par le
backend), même principe que `drift.drift_detector.DriftDetector`.
"""

from __future__ import annotations

from shared.ai_engine.retraining.rules import ALL_RULES
from shared.ai_engine.retraining.types import (
    RetrainingDecision,
    RetrainingDecisionResult,
    RetrainingRulesConfig,
    RetrainingSignals,
)


class DecisionEngine:
    """Évalue toutes les règles configurées et retient la décision la plus sévère."""

    def __init__(self, config: RetrainingRulesConfig | None = None) -> None:
        self._config = config or RetrainingRulesConfig()

    def evaluate(self, signals: RetrainingSignals) -> RetrainingDecisionResult:
        outcomes = tuple(
            outcome
            for outcome in (rule(signals, self._config) for rule in ALL_RULES)
            if outcome is not None
        )
        triggered = tuple(outcome for outcome in outcomes if outcome.triggered)
        decision = (
            max(outcome.decision for outcome in outcomes)
            if outcomes
            else RetrainingDecision.NO_ACTION
        )
        return RetrainingDecisionResult(decision=decision, outcomes=outcomes, triggered_rules=triggered)
