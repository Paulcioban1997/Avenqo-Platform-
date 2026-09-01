"""Catalogue des offres d'abonnement Avenqo indÃ©pendant de Stripe."""

from dataclasses import dataclass
from enum import StrEnum


class PlanCode(StrEnum):
    """Codes stables utilisÃ©s par Avenqo et les futurs adaptateurs de paiement."""

    DEMO = "demo"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM_ENTERPRISE = "custom_enterprise"


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    """DÃ©crit une offre sans dÃ©pendre d'un fournisseur de paiement."""

    code: PlanCode
    name: str
    selectable_modules: frozenset[str]
    max_selectable_modules: int | None = None
    requires_sales_contact: bool = False
    monthly_price_usd: int | None = None

    def allows_module(self, module_code: str) -> bool:
        """Indique si le module peut Ãªtre choisi avec cette offre."""

        return module_code in self.selectable_modules

    def allows_selection(self, module_codes: set[str]) -> bool:
        if not module_codes.issubset(self.selectable_modules):
            return False
        return (
            self.max_selectable_modules is None
            or len(module_codes) <= self.max_selectable_modules
        )


MODULE_NAMES: dict[str, str] = {
    "retail": "Retail Intelligence",
    "marketing": "Marketing AI",
    "crm": "CRM AI",
    "hr": "HR AI",
    "accounting": "Accounting AI",
    "ocr": "OCR AI",
    "voice": "Voice AI",
    "media": "Media AI",
    "legal": "Legal AI",
    "appointments": "Appointments AI",
    "workflow": "Workflow Automation",
}
ALL_MODULES = frozenset(MODULE_NAMES)

PUBLIC_PLANS: tuple[SubscriptionPlan, ...] = (
    SubscriptionPlan(
        PlanCode.DEMO,
        "Demo",
        ALL_MODULES,
        max_selectable_modules=2,
        monthly_price_usd=28,
    ),
    SubscriptionPlan(
        PlanCode.PROFESSIONAL,
        "Professional",
        ALL_MODULES,
        max_selectable_modules=8,
        monthly_price_usd=49,
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
    credits: int
    price_usd: int


AI_CREDIT_PACKS: tuple[AICreditPack, ...] = (
    AICreditPack("starter", credits=5_000, price_usd=10),
    AICreditPack("growth", credits=20_000, price_usd=29),
    AICreditPack("scale", credits=50_000, price_usd=59),
    AICreditPack("volume", credits=150_000, price_usd=149),
)
AI_CREDIT_PACKS_BY_CODE = {pack.code: pack for pack in AI_CREDIT_PACKS}


def get_plan(code: PlanCode | str) -> SubscriptionPlan:
    """Retourne l'offre correspondant Ã  son code stable."""

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
    PlanCode.DEMO: DataImportLimits(max_datasets=5, max_file_mb=10),
    PlanCode.PROFESSIONAL: DataImportLimits(max_datasets=50, max_file_mb=100),
    PlanCode.ENTERPRISE: DataImportLimits(max_datasets=500, max_file_mb=250),
    PlanCode.CUSTOM_ENTERPRISE: DataImportLimits(max_datasets=500, max_file_mb=250),
}


def data_import_limits_for(code: PlanCode | str) -> DataImportLimits:
    """Retourne les limites d'import pour une offre ; retombe sur Demo si inconnue."""

    try:
        return DATA_IMPORT_LIMITS_BY_PLAN[PlanCode(code)]
    except (KeyError, ValueError):
        return DATA_IMPORT_LIMITS_BY_PLAN[PlanCode.DEMO]