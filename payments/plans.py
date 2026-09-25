"""Catalogue des offres d'abonnement Avenqo indépendant de Stripe."""

from dataclasses import dataclass
from enum import StrEnum

from modules.registry import BUSINESS_MODULE_REGISTRY


class PlanCode(StrEnum):
    """Codes stables utilisés par Avenqo et les futurs adaptateurs de paiement."""

    BASE = "base"
    DEMO = "demo"  # Alias rétrocompatible pour migration transparente
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM_ENTERPRISE = "custom_enterprise"


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    """Décrit une offre sans dépendre d'un fournisseur de paiement."""

    code: PlanCode
    name: str
    selectable_modules: frozenset[str]
    max_selectable_modules: int | None = None
    requires_sales_contact: bool = False
    monthly_price_usd: float | None = None
    monthly_ai_credits: int | None = None

    def allows_module(self, module_code: str) -> bool:
        """Indique si le module peut être choisi avec cette offre."""

        return module_code in self.selectable_modules

    def allows_selection(self, module_codes: set[str]) -> bool:
        if not module_codes.issubset(self.selectable_modules):
            return False
        return (
            self.max_selectable_modules is None
            or len(module_codes) <= self.max_selectable_modules
        )


MODULE_NAMES = {module.key: module.display_name for module in BUSINESS_MODULE_REGISTRY}
ALL_MODULES = frozenset(MODULE_NAMES)

PUBLIC_PLANS: tuple[SubscriptionPlan, ...] = (
    SubscriptionPlan(
        PlanCode.BASE,
        "Base",
        ALL_MODULES,
        max_selectable_modules=3,
        monthly_price_usd=29.99,
        monthly_ai_credits=6_500,
    ),
    SubscriptionPlan(
        PlanCode.PROFESSIONAL,
        "Professional",
        ALL_MODULES,
        max_selectable_modules=6,
        monthly_price_usd=49.99,
        monthly_ai_credits=25_000,
    ),
    SubscriptionPlan(
        PlanCode.ENTERPRISE,
        "Enterprise",
        ALL_MODULES,
        requires_sales_contact=True,
    ),
)

INTERNAL_COMPATIBILITY_PLANS: tuple[SubscriptionPlan, ...] = (
    *PUBLIC_PLANS,
    SubscriptionPlan(
        PlanCode.DEMO,
        "Base",
        ALL_MODULES,
        max_selectable_modules=3,
        monthly_price_usd=29.99,
        monthly_ai_credits=6_500,
    ),
    SubscriptionPlan(
        PlanCode.CUSTOM_ENTERPRISE,
        "Custom Enterprise",
        ALL_MODULES,
        requires_sales_contact=True,
    ),
)

PLANS = PUBLIC_PLANS
PLANS_BY_CODE = {plan.code: plan for plan in INTERNAL_COMPATIBILITY_PLANS}


@dataclass(frozen=True, slots=True)
class AICreditPack:
    code: str
    plan_code: PlanCode
    credits: int
    price_usd: int


AI_CREDIT_PACKS: tuple[AICreditPack, ...] = (
    AICreditPack("credits_6500", PlanCode.BASE, credits=6_500, price_usd=10),
    AICreditPack("credits_25000", PlanCode.PROFESSIONAL, credits=25_000, price_usd=35),
    AICreditPack("credits_65000", PlanCode.PROFESSIONAL, credits=65_000, price_usd=80),
    # Rétrocompatibilité
    AICreditPack("demo_extra", PlanCode.BASE, credits=6_500, price_usd=10),
    AICreditPack("professional_6500", PlanCode.PROFESSIONAL, credits=6_500, price_usd=10),
    AICreditPack("professional_25000", PlanCode.PROFESSIONAL, credits=25_000, price_usd=35),
)
AI_CREDIT_PACKS_BY_CODE = {pack.code: pack for pack in AI_CREDIT_PACKS}
# Preserve delayed Checkout sessions created before the Phase 2 code rename.
AI_CREDIT_PACKS_BY_CODE["professional_extra"] = AI_CREDIT_PACKS_BY_CODE["credits_25000"]


def get_plan(code: PlanCode | str) -> SubscriptionPlan:
    """Retourne l'offre correspondant à son code stable."""

    try:
        return PLANS_BY_CODE[PlanCode(code)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Offre Avenqo inconnue : {code}") from exc


def get_ai_credit_pack(code: str) -> AICreditPack:
    try:
        return AI_CREDIT_PACKS_BY_CODE[code]
    except KeyError as exc:
        raise ValueError(f"Pack de crédits Avenqo inconnu : {code}") from exc


@dataclass(frozen=True, slots=True)
class DataImportLimits:
    """Limites CORE d'import de données (indépendantes des modules optionnels).

    L'import de données est une capacité de plateforme disponible sur toute
    offre payante (Demo compris) ; seules ces limites varient par offre.
    Valeurs par défaut techniques, ajustables sans changement de code via
    `Settings` — pas des tarifs commerciaux définitifs.
    """

    max_datasets: int
    max_file_mb: int


DATA_IMPORT_LIMITS_BY_PLAN: dict[PlanCode, DataImportLimits] = {
    PlanCode.BASE: DataImportLimits(max_datasets=25, max_file_mb=50),
    PlanCode.DEMO: DataImportLimits(max_datasets=25, max_file_mb=50),
    PlanCode.PROFESSIONAL: DataImportLimits(max_datasets=100, max_file_mb=100),
    PlanCode.ENTERPRISE: DataImportLimits(max_datasets=1000, max_file_mb=250),
    PlanCode.CUSTOM_ENTERPRISE: DataImportLimits(max_datasets=1000, max_file_mb=250),
}


def data_import_limits_for(code: PlanCode | str) -> DataImportLimits:
    """Retourne les limites d'import pour une offre ; retombe sur Base si inconnue."""

    try:
        norm = PlanCode(str(code).lower())
        return DATA_IMPORT_LIMITS_BY_PLAN.get(norm, DATA_IMPORT_LIMITS_BY_PLAN[PlanCode.BASE])
    except (KeyError, ValueError):
        return DATA_IMPORT_LIMITS_BY_PLAN[PlanCode.BASE]
