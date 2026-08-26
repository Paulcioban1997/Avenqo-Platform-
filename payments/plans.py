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
    requires_sales_contact: bool = False
    monthly_price_usd: int | None = None

    def allows_module(self, module_code: str) -> bool:
        """Indique si le module peut Ãªtre choisi avec cette offre."""

        return module_code in self.selectable_modules


RETAIL_MODULES = frozenset({"retail"})

PLANS: tuple[SubscriptionPlan, ...] = (
    SubscriptionPlan(PlanCode.DEMO, "Demo", RETAIL_MODULES, monthly_price_usd=28),
    SubscriptionPlan(PlanCode.PROFESSIONAL, "Professional", RETAIL_MODULES, monthly_price_usd=99),
    SubscriptionPlan(PlanCode.ENTERPRISE, "Enterprise", RETAIL_MODULES, monthly_price_usd=499),
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