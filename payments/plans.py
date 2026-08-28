"""Catalogue commercial Avenqo indépendant de Stripe."""

from dataclasses import dataclass
from enum import StrEnum


class PlanCode(StrEnum):
    """Codes stables utilisés par Avenqo et les adaptateurs de paiement."""

    DEMO = "demo"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM_ENTERPRISE = "custom_enterprise"


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    """Décrit une offre sans dépendre d'un fournisseur de paiement."""

    code: PlanCode
    name: str
    selectable_modules: frozenset[str]
    requires_sales_contact: bool = False
    monthly_price_usd: int | None = None
    included_ai_credits: int | None = None

    def allows_module(self, module_code: str) -> bool:
        return module_code in self.selectable_modules


@dataclass(frozen=True, slots=True)
class AICreditPack:
    """Pack de crédits IA acheté une seule fois et conservé jusqu'à utilisation."""

    code: str
    credits: int
    price_usd: int


RETAIL_MODULES = frozenset({"retail"})
ENTERPRISE_STARTING_PRICE_USD = 250

PUBLIC_PLANS: tuple[SubscriptionPlan, ...] = (
    SubscriptionPlan(
        PlanCode.DEMO,
        "Demo",
        RETAIL_MODULES,
        monthly_price_usd=28,
        included_ai_credits=5_000,
    ),
    SubscriptionPlan(
        PlanCode.PROFESSIONAL,
        "Professional",
        RETAIL_MODULES,
        monthly_price_usd=49,
        included_ai_credits=25_000,
    ),
    SubscriptionPlan(
        PlanCode.ENTERPRISE,
        "Enterprise",
        RETAIL_MODULES,
        requires_sales_contact=True,
        included_ai_credits=None,
    ),
)

INTERNAL_COMPATIBILITY_PLANS: tuple[SubscriptionPlan, ...] = (
    *PUBLIC_PLANS,
    SubscriptionPlan(
        PlanCode.CUSTOM_ENTERPRISE,
        "Custom Enterprise",
        RETAIL_MODULES,
        requires_sales_contact=True,
        included_ai_credits=None,
    ),
)

PLANS = PUBLIC_PLANS
PLANS_BY_CODE = {plan.code: plan for plan in INTERNAL_COMPATIBILITY_PLANS}

AI_CREDIT_PACKS: tuple[AICreditPack, ...] = (
    AICreditPack("credits_5k", 5_000, 10),
    AICreditPack("credits_20k", 20_000, 29),
    AICreditPack("credits_50k", 50_000, 59),
    AICreditPack("credits_150k", 150_000, 149),
)
AI_CREDIT_PACKS_BY_CODE = {pack.code: pack for pack in AI_CREDIT_PACKS}


def get_plan(code: PlanCode | str) -> SubscriptionPlan:
    try:
        return PLANS_BY_CODE[PlanCode(code)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Offre Avenqo inconnue : {code}") from exc


def get_credit_pack(code: str) -> AICreditPack:
    try:
        return AI_CREDIT_PACKS_BY_CODE[code]
    except KeyError as exc:
        raise ValueError(f"Pack de crédits IA inconnu : {code}") from exc


@dataclass(frozen=True, slots=True)
class DataImportLimits:
    """Limites CORE d'import de données indépendantes des modules optionnels."""

    max_datasets: int
    max_file_mb: int


DATA_IMPORT_LIMITS_BY_PLAN: dict[PlanCode, DataImportLimits] = {
    PlanCode.DEMO: DataImportLimits(max_datasets=5, max_file_mb=10),
    PlanCode.PROFESSIONAL: DataImportLimits(max_datasets=50, max_file_mb=100),
    PlanCode.ENTERPRISE: DataImportLimits(max_datasets=500, max_file_mb=250),
    PlanCode.CUSTOM_ENTERPRISE: DataImportLimits(max_datasets=500, max_file_mb=250),
}


def data_import_limits_for(code: PlanCode | str) -> DataImportLimits:
    try:
        return DATA_IMPORT_LIMITS_BY_PLAN[PlanCode(code)]
    except (KeyError, ValueError):
        return DATA_IMPORT_LIMITS_BY_PLAN[PlanCode.DEMO]
