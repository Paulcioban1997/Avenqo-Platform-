"""Catalogue des offres d'abonnement Avenqo indÃ©pendant de Stripe."""

from dataclasses import dataclass
from enum import StrEnum


class PlanCode(StrEnum):
    """Codes stables utilisÃ©s par Avenqo et les futurs adaptateurs de paiement."""

    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM_ENTERPRISE = "custom_enterprise"


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    """DÃ©crit une offre sans dÃ©pendre d'un fournisseur de paiement."""

    code: PlanCode
    name: str
    selectable_modules: frozenset[str]
    requires_sales_contact: bool = False

    def allows_module(self, module_code: str) -> bool:
        """Indique si le module peut Ãªtre choisi avec cette offre."""

        return module_code in self.selectable_modules


RETAIL_MODULES = frozenset({"retail"})

PLANS: tuple[SubscriptionPlan, ...] = (
    SubscriptionPlan(PlanCode.STARTER, "Starter", RETAIL_MODULES),
    SubscriptionPlan(PlanCode.PROFESSIONAL, "Professional", RETAIL_MODULES),
    SubscriptionPlan(PlanCode.ENTERPRISE, "Enterprise", RETAIL_MODULES),
    SubscriptionPlan(
        PlanCode.CUSTOM_ENTERPRISE,
        "Custom Enterprise",
        RETAIL_MODULES,
        requires_sales_contact=True,
    ),
)

PLANS_BY_CODE = {plan.code: plan for plan in PLANS}


def get_plan(code: PlanCode | str) -> SubscriptionPlan:
    """Retourne l'offre correspondant Ã  son code stable."""

    try:
        return PLANS_BY_CODE[PlanCode(code)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Offre Avenqo inconnue : {code}") from exc
