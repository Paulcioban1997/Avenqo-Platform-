"""Agrégation multi-capacités — le cœur générique ne connaît AUCUNE règle de module.

Registre VIDE par défaut : chaque module enregistre ses propres règles (voir
`modules/retailsense/decision_policies.py`), typées uniquement par capacité IA
générique (jamais par ``if module_code == "retail"``).
"""

from __future__ import annotations

from typing import Callable, Sequence

from shared.ai_engine.decision_intelligence.contracts import BusinessInsight, BusinessSignal

CrossCapabilityRule = Callable[[Sequence[BusinessSignal]], "BusinessInsight | None"]


class CrossCapabilityRuleRegistry:
    """Vide par défaut : le moteur générique ne contient aucune règle métier."""

    def __init__(self) -> None:
        self._rules: list[CrossCapabilityRule] = []

    def register(self, rule: CrossCapabilityRule) -> None:
        self._rules.append(rule)

    def evaluate(self, signals: Sequence[BusinessSignal]) -> tuple[BusinessInsight, ...]:
        insights = []
        for rule in self._rules:
            insight = rule(signals)
            if insight is not None:
                insights.append(insight)
        return tuple(insights)
