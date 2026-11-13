"""Tenant-scoped spoken answers that must not depend on model routing.

Module discovery uses the authenticated employee's company entitlements.
Catalog answers use that same company's retail records. Nothing is invented,
and another tenant's rows are never readable from a different company id.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session


def _words(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return set(re.findall(r"[a-z0-9]+", ascii_text))


def is_module_access_question(text: str) -> bool:
    words = _words(text)
    if words & {"contrat", "contrats", "contract", "contracts", "clause", "clauses", "nda", "juridique", "avocat"}:
        return False
    modules = bool(words & {"module", "modules", "fonctionnalite", "fonctionnalites"})
    access = bool(words & {
        "accessible", "accessibles", "disponible", "disponibles", "actif", "actifs",
        "inclus", "incluse", "incluses", "abonnement", "subscription", "entreprise", "avenqo",
    })
    return modules and access


def is_open_catalog_question(text: str) -> bool:
    words = _words(text)
    products = bool(words & {"produit", "produits", "product", "products", "article", "articles", "catalogue", "catalog"})
    if not products:
        return False
    listing = bool(words & {"quels", "quelles", "quel", "liste", "what", "which", "catalogue", "catalog"})
    for_sale = bool(words & {"vente", "vendre", "sale", "sales"})
    prices = bool(words & {"prix", "price", "prices", "tarif", "tarifs"})
    if words & {"stock", "inventaire", "inventory"} and not prices and "vente" not in words and not listing:
        return False
    return (listing or for_sale) and (prices or for_sale or listing)


def spoken_module_answer(names: list[str], *, plan_code: str | None, locale: str) -> str:
    french = locale.lower().startswith("fr")
    unique = []
    for name in names:
        cleaned = str(name).strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    plan = (plan_code or "").strip()
    if french:
        if not unique:
            base = "Votre entreprise n'a actuellement aucun module actif."
        else:
            base = "Votre entreprise dispose actuellement des modules suivants : " + ", ".join(unique) + "."
        if plan:
            return f"Votre abonnement {plan} est actif. {base}"
        return base
    if not unique:
        base = "Your company does not currently have any active modules."
    else:
        base = "Your company currently has these modules: " + ", ".join(unique) + "."
    if plan:
        return f"Your {plan} subscription is active. {base}"
    return base


def spoken_catalog_answer(
    products: list[dict[str, Any]],
    *,
    retail_enabled: bool,
    locale: str,
    currency: str | None = None,
) -> str:
    french = locale.lower().startswith("fr")
    if not retail_enabled:
        return (
            "Le catalogue de vente n'est pas disponible pour votre entreprise."
            if french else
            "The sales catalog is not available for your company."
        )
    rows = [row for row in products if isinstance(row, dict) and str(row.get("name") or "").strip()]
    if not rows:
        return (
            "Le catalogue ne contient actuellement aucun produit en vente."
            if french else
            "The catalog does not currently list any products for sale."
        )
    spoken = []
    for row in rows[:5]:
        name = str(row["name"]).strip()
        price = row.get("price")
        unit = str(row.get("currency") or currency or "").strip()
        if price is None or price == "":
            price_text = "prix non indiqué" if french else "price not listed"
        else:
            price_text = f"{price} {unit}".strip()
        available = ""
        inventory = row.get("inventory_count")
        if row.get("in_stock") is True and isinstance(inventory, (int, float)) and inventory > 0:
            available = ", disponible" if french else ", available"
        spoken.append(f"{name}, {price_text}{available}")
    extra = ""
    if len(rows) > 5:
        extra = (
            f" Et {len(rows) - 5} autre{'s' if len(rows) - 5 > 1 else ''} article{'s' if len(rows) - 5 > 1 else ''} au catalogue."
            if french else
            f" And {len(rows) - 5} more items in the catalog."
        )
    if french:
        return "Nous avons en vente : " + " ; ".join(spoken) + "." + extra
    return "We currently have for sale: " + "; ".join(spoken) + "." + extra


def resolve_direct_voice_answer(
    db: Session | None,
    *,
    company_id: UUID,
    transcript: str,
    authenticated_staff: bool,
    staff_role: str | None,
    locale: str,
) -> str | None:
    """Return a spoken answer, or None when Central AI should handle the turn."""
    if is_module_access_question(transcript):
        if not authenticated_staff or not staff_role:
            if locale.lower().startswith("fr"):
                return "Cette information est réservée aux employés authentifiés de votre entreprise."
            return "That information is reserved for authenticated employees of your company."
        from backend.app.services.module_entitlement_service import ModuleEntitlementService
        from shared.ai_engine.contracts import TenantContext

        summary = ModuleEntitlementService(db).summary(TenantContext(company_id))
        names = [item.display_name for item in summary.modules if item.active and item.display_name]
        if not names:
            names = list(summary.active_modules)
        return spoken_module_answer(names, plan_code=summary.plan_code, locale=locale)

    if not is_open_catalog_question(transcript):
        return None
    from backend.app.services.company_intelligence_service import CompanyIntelligenceService

    profile = CompanyIntelligenceService(db).get_profile(company_id)
    retail_enabled = bool(getattr(profile, "has_retail_commerce", False)) or "retail" in set(getattr(profile, "active_modules", ()) or ())
    products = list(getattr(profile, "public_products", ()) or ())
    return spoken_catalog_answer(
        products,
        retail_enabled=retail_enabled,
        locale=locale,
        currency=getattr(profile, "currency_code", None),
    )
