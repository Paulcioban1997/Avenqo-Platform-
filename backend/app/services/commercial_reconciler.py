"""Service de réconciliation du bordereau de commande commerciale Avenqo.

Assure la concordance stricte entre les engagements contractuels, le catalogue
canonique des offres (payments.plans), les limites d'attribution (modules & crédits IA)
et les identifiants de tarification Stripe configurés.
En cas de divergence, lève ou signale un état COMMERCIAL_CONFIG_MISMATCH bloquant
la signature et l'activation commerciale.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from backend.app.config.settings import Settings, get_settings
from backend.app.models.company import Company
from payments.plans import PlanCode, get_plan, PUBLIC_PLANS


@dataclass(frozen=True, slots=True)
class CommercialOrderSchedule:
    """Bordereau de commande commerciale dynamique et certifié."""

    plan_code: str
    plan_name: str
    monthly_price: float | None
    currency: str
    billing_cycle: str
    max_selectable_modules: int | None
    selected_modules: list[str]
    included_ai_credits: int | None
    extra_credits_terms: str
    applicable_taxes: str
    renewal_terms: str
    effective_date: str
    reconciliation_status: str  # "RECONCILED" | "COMMERCIAL_CONFIG_MISMATCH"
    mismatches: list[str]
    is_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CommercialReconciler:
    """Vérifie la cohérence entre le contrat, l'offre souscrite et l'infrastructure de facturation."""

    @classmethod
    def reconcile(
        cls,
        company: Company,
        settings: Settings | None = None,
    ) -> CommercialOrderSchedule:
        if settings is None:
            settings = get_settings()

        mismatches: list[str] = []
        raw_plan = (company.subscription_plan or "base").lower()
        currency = (company.currency_code or "CAD").upper()

        # 1. Résolution de l'offre canonique
        try:
            plan = get_plan(raw_plan)
        except ValueError:
            mismatches.append(f"Offre inconnue ou non répertoriée au catalogue canonique : {raw_plan}")
            plan = get_plan(PlanCode.BASE)

        # 2. Validation des prix de référence
        monthly_price = plan.monthly_price_cad if currency == "CAD" else plan.monthly_price_usd
        if plan.code == PlanCode.BASE:
            expected_cad = 29.99
            expected_credits = 6_500
            expected_max_modules = 2
            if currency == "CAD" and plan.monthly_price_cad != expected_cad:
                mismatches.append(f"Prix Base divergent : {plan.monthly_price_cad} CAD attendu {expected_cad} CAD")
        elif plan.code == PlanCode.PROFESSIONAL:
            expected_cad = 49.99
            expected_credits = 20_000
            expected_max_modules = 5
            if currency == "CAD" and plan.monthly_price_cad != expected_cad:
                mismatches.append(f"Prix Professional divergent : {plan.monthly_price_cad} CAD attendu {expected_cad} CAD")
        elif plan.code in (PlanCode.ENTERPRISE, PlanCode.CUSTOM_ENTERPRISE):
            expected_credits = None
            expected_max_modules = None
        else:
            expected_credits = plan.monthly_ai_credits
            expected_max_modules = plan.max_selectable_modules

        # 3. Validation des modules actifs du locataire
        active_modules = [
            cm.module.name if cm.module else str(cm.module_id)
            for cm in (company.company_modules or [])
            if getattr(cm, "status", None) and str(getattr(cm.status, "value", cm.status)).upper() == "ACTIVE"
        ]
        if expected_max_modules is not None and len(active_modules) > expected_max_modules:
            mismatches.append(
                f"Dépassement du quota de modules : {len(active_modules)} modules actifs pour un plafond de {expected_max_modules}"
            )

        # 4. Validation des identifiants Stripe configurés (si Stripe activé)
        if settings.stripe_secret_key:
            price_id = settings.stripe_price_id(raw_plan, currency)
            if not price_id and plan.code not in (PlanCode.ENTERPRISE, PlanCode.CUSTOM_ENTERPRISE):
                mismatches.append(
                    f"Identifiant de prix Stripe manquant pour le forfait {raw_plan} en devise {currency}"
                )

        # 5. Définition des conditions fiscales et de renouvellement
        tax_terms = (
            f"TPS (5 %) et TVQ (9,975 %) applicables selon les lois du Québec et du Canada (Devise : {currency})"
            if currency == "CAD"
            else f"Taxes applicables selon la juridiction locale du client (Devise : {currency})"
        )

        renewal_terms = (
            "Renouvellement mensuel automatique par tacite reconduction au terme de chaque période de facturation. "
            "Résiliation libre et sans frais à tout moment depuis le portail de facturation client, effective à la fin du cycle payé."
        )

        # Add-ons are a separate voluntary checkout. Never embed stale catalog
        # amounts in the recurring agreement or imply automatic overage charges.
        extra_credits_terms = (
            "Les crédits additionnels sont optionnels, achetés séparément au tarif affiché avant paiement. "
            "Aucun dépassement n'est facturé automatiquement."
        )

        effective_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        is_blocked = len(mismatches) > 0
        reconciliation_status = "COMMERCIAL_CONFIG_MISMATCH" if is_blocked else "RECONCILED"

        return CommercialOrderSchedule(
            plan_code=str(plan.code),
            plan_name=plan.name,
            monthly_price=monthly_price,
            currency=currency,
            billing_cycle="Mensuel (renouvelable)",
            max_selectable_modules=expected_max_modules,
            selected_modules=active_modules,
            included_ai_credits=expected_credits,
            extra_credits_terms=extra_credits_terms,
            applicable_taxes=tax_terms,
            renewal_terms=renewal_terms,
            effective_date=effective_date,
            reconciliation_status=reconciliation_status,
            mismatches=mismatches,
            is_blocked=is_blocked,
        )
