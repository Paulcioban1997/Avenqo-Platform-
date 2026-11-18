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
    products = bool(words & {
        "produit", "produits", "product", "products", "article", "articles",
        "catalogue", "catalog", "catalogs", "catalogues", "item", "items",
        "planche", "planches", "snowboard", "snowboards",
    })
    if not products:
        return False
    listing = bool(words & {
        "quels", "quelles", "quel", "quelle", "liste", "what", "which",
        "catalogue", "catalog", "chacun", "chacune", "tous", "toutes", "all", "every", "each",
    })
    for_sale = bool(words & {"vente", "vendre", "sale", "sales"})
    prices = bool(words & {"prix", "price", "prices", "tarif", "tarifs", "combien", "cout"})
    stock_inquiry = bool(words & {
        "stock", "stocks", "inventaire", "inventory", "disponible", "disponibles",
        "disponibilite", "disponibilites", "restant", "restants",
    })
    return listing or for_sale or prices or stock_inquiry


def spoken_module_answer(names: list[str], *, plan_code: str | None, locale: str) -> str:
    loc = locale.lower()
    french = loc.startswith("fr")
    romanian = loc.startswith("ro")
    unique = []
    for name in names:
        cleaned = str(name).strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    plan = (plan_code or "").strip()
    if romanian:
        if not unique:
            base = "Compania dumneavoastră nu are în prezent niciun modul activ."
        else:
            base = "Compania dumneavoastră dispune în prezent de următoarele module: " + ", ".join(unique) + "."
        if plan:
            return f"Abonamentul dumneavoastră {plan} este activ. {base}"
        return base
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
    products: Any,
    *,
    retail_enabled: bool,
    locale: str,
    currency: str | None = None,
) -> str:
    loc = locale.lower()
    french = loc.startswith("fr")
    romanian = loc.startswith("ro")
    if not retail_enabled:
        if romanian:
            return "Catalogul de vânzări nu este disponibil pentru compania dumneavoastră."
        return (
            "Le catalogue de vente n'est pas disponible pour votre entreprise."
            if french else
            "The sales catalog is not available for your company."
        )
    rows = [row for row in products if isinstance(row, dict) and str(row.get("name") or "").strip()]
    if not rows:
        if romanian:
            return "Catalogul nu conține în prezent niciun produs de vânzare."
        return (
            "Le catalogue ne contient actuellement aucun produit en vente."
            if french else
            "The catalog does not currently list any products for sale."
        )
    spoken = []
    for row in rows[:5]:
        name = str(row["name"]).strip()
        price = row.get("price")
        raw_unit = str(row.get("currency") or currency or "").strip().upper()
        if raw_unit in ("CAD", "USD", "$") or not raw_unit:
            unit = "$"
        elif raw_unit in ("EUR", "€"):
            unit = "€"
        elif raw_unit in ("GBP", "£"):
            unit = "£"
        else:
            unit = raw_unit
        is_live = row.get("is_live_stock") is True
        freshness = str(row.get("freshness_status") or "").upper()
        if price is None or price == "":
            price_text = "preț nespecificat" if romanian else ("prix non indiqué" if french else "price not listed")
        else:
            price_text = f"{price} {unit}".strip()
            if row.get("price_status") == "historical_catalog" or not is_live:
                hist_tag = " (preț de referință)" if romanian else (" (prix indicatif)" if french else " (reference price)")
                price_text += hist_tag

        available = ""
        inventory = row.get("inventory_count")
        stock_avail = row.get("stock_availability")
        if is_live and (stock_avail == "IN_STOCK" or row.get("in_stock") is True):
            available = ", disponibil" if romanian else (", disponible" if french else ", available")
        elif is_live and (stock_avail == "OUT_OF_STOCK" or row.get("in_stock") is False):
            available = ", stoc epuizat" if romanian else (", en rupture de stock" if french else ", out of stock")
        elif freshness == "STALE":
            available = ", date de stoc expirate" if romanian else (", données de stock non récentes" if french else ", stock data stale")
        elif freshness == "UNAVAILABLE":
            available = ", stoc indisponibil" if romanian else (", stock indisponible" if french else ", stock unavailable")
        elif freshness == "SYNCING":
            available = ", sincronizare stoc în curs" if romanian else (", synchronisation de stock en cours" if french else ", stock syncing in progress")
        elif freshness == "UNCONFIRMED_HISTORICAL":
            available = ", stoc nesincronizat" if romanian else (", stock en direct non synchronisé" if french else ", live stock unconfirmed")
        else:
            available = ", stoc direct neconfirmat" if romanian else (", stock direct non confirmé" if french else ", live stock unconfirmed")
        spoken.append(f"{name}, {price_text}{available}")
    extra = ""
    if len(rows) > 5:
        remaining = len(rows) - 5
        if romanian:
            extra = f" Și încă {remaining} {'articol' if remaining == 1 else 'articole'} în catalog."
        elif french:
            extra = f" Et {remaining} autre{'s' if remaining > 1 else ''} article{'s' if remaining > 1 else ''} au catalogue."
        else:
            extra = f" And {remaining} more items in the catalog."
    if romanian:
        return "Avem în catalog: " + " ; ".join(spoken) + "." + extra
    if french:
        return "Nous avons au catalogue : " + " ; ".join(spoken) + "." + extra
    return "In our catalog, we have: " + "; ".join(spoken) + "." + extra


def resolve_direct_voice_answer(
    db: Session | None,
    *,
    company_id: UUID,
    transcript: str,
    authenticated_staff: bool = False,
    staff_role: str | None = None,
    locale: str = "en",
) -> str | None:
    """Return a spoken answer, or None when Central AI should handle the turn."""
    if db is None:
        return None
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
