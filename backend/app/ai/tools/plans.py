"""Comparaison centralisée des niveaux d'abonnement (Phase 30).

Aucun code appelant ne doit comparer directement des chaînes de plan
(`if plan == "enterprise"`) : tout passe par `plan_meets_minimum`.
"""

from __future__ import annotations

from payments.plans import PlanCode

# Ordre croissant : un plan à droite inclut les capacités des plans à gauche.
_PLAN_RANK: dict[str, int] = {
    PlanCode.DEMO.value: 0,
    PlanCode.PROFESSIONAL.value: 1,
    PlanCode.ENTERPRISE.value: 2,
    PlanCode.CUSTOM_ENTERPRISE.value: 2,
}


def plan_meets_minimum(plan_code: str | None, minimum_plan: str | None) -> bool:
    """Indique si `plan_code` satisfait au moins `minimum_plan`.

    Si `minimum_plan` est None, l'outil est disponible pour tout plan actif.
    Un `plan_code` inconnu ou absent est traité comme le rang le plus bas.
    """

    if minimum_plan is None:
        return True
    current_rank = _PLAN_RANK.get((plan_code or "").lower(), 0)
    required_rank = _PLAN_RANK.get(minimum_plan.lower(), 0)
    return current_rank >= required_rank
